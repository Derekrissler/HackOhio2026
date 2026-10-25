"""Fictional B-to-D handoff, review, publication and authorized display integration."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from pydantic import ValidationError

from app.analytics.cluster_review import ClusterReview, approved_ids
from app.analytics.config import AnalyticsConfig
from app.analytics.evidence_repository import SupabaseEvidenceRepository
from app.analytics.error_handoff import completion_metadata
from app.analytics.ml_readiness import ml_readiness
from app.analytics.repository import SupabaseAnalysisRepository
from app.analytics.reviewed_excerpts import ReviewedExcerptExport
from app.analytics.service import _adapt, analyze_course, persist_analysis
from app.analytics.dashboard import load_dashboard
from .test_persistence import Client, database, NOW
from .test_clustering import FixtureEmbedder

FOLDER = Path(__file__).parent / 'fixtures'


class TwoFamilies(FixtureEmbedder):
    def encode(self, texts):
        return np.array([[1., 0, 0] if 'inequality' in text else [0, 1., 0] for text in texts])


def source():
    rows = json.loads((FOLDER / 'error_handoff.json').read_text())
    export = ReviewedExcerptExport.model_validate_json((FOLDER / 'reviewed_errors.json').read_text())
    data = {name: [] for name in database()}
    cid = str(export.course_id)
    seen = {name: set() for name in data}
    entries = {str(entry.ler_id): entry for entry in export.entries}

    def add(table, value, key='id'):
        identity = value[key] if isinstance(key, str) else tuple(value[k] for k in key)
        if identity not in seen[table]:
            data[table].append(value)
            seen[table].add(identity)

    for envelope in rows:
        ler = deepcopy(envelope['ler'])
        entry = entries.get(ler['id'])
        meta = {'schema_version': '1.0', 'errors_analyzed': envelope['errors_analyzed'],
                'error_outcomes': {str(entry.ler_error_id): [m['outcome_id'] for m in envelope['outcome_mappings']]} if entry else {}}
        ler['payload'] = {'analytics_v1': meta}
        add('lers', ler)
        add('learners', {'id': ler['learner_id'], 'course_id': cid})
        add('assessments', {**envelope['assessment'], 'course_id': cid})
        add('questions', {**envelope['question'], 'course_id': cid, 'assessment_id': ler['assessment_id'], 'code': 'Q' + ler['question_id'][-1]})
        add('attempts', {**envelope['attempt'], 'course_id': cid, 'assessment_id': ler['assessment_id'], 'learner_id': ler['learner_id']})
        add('responses', {**envelope['response'], 'course_id': cid, 'attempt_id': ler['attempt_id'], 'question_id': ler['question_id'],
                          'learner_id': ler['learner_id'], 'updated_at': NOW, 'content_hash': ler['response_id']})
        for ref in envelope['evidence_ref_ids']:
            add('evidence_refs', {'id': ref, 'course_id': cid, 'learner_id': ler['learner_id'], 'content_hash': ref,
                                 'source_type': 'manual', 'excerpt': 'Fictional supporting annotation.', 'page': 1})
            add('ler_evidence', {'ler_id': ler['id'], 'evidence_ref_id': ref, 'role': 'feedback'}, ('ler_id', 'evidence_ref_id'))
        for mapping in envelope['outcome_mappings']:
            add('outcomes', {'id': mapping['outcome_id'], 'course_id': cid, 'code': 'LO' + mapping['outcome_id'][-1]})
            add('question_outcomes', {'question_id': ler['question_id'], **mapping}, ('question_id','outcome_id'))
        if entry:
            add('ler_errors', {'id': str(entry.ler_error_id), 'ler_id': ler['id'], 'code': entry.error_code, 'instructor_status': 'confirmed'})
            for ref in entry.evidence_ref_ids:
                add('ler_error_evidence', {'ler_error_id': str(entry.ler_error_id), 'evidence_ref_id': str(ref)}, ('ler_error_id','evidence_ref_id'))
    sdk = Client(data)
    return sdk, SupabaseAnalysisRepository(sdk), export


def reviewed_run(repo, export, embedder=None):
    args = dict(cluster=True, reviewed_export=export, embedder=embedder or TwoFamilies())
    candidate = analyze_course(repo, export.course_id, **args)
    review = ClusterReview.model_validate(candidate.manifest['cluster_review_template'])
    review.reviewer_ref = 'fictional-cluster-reviewer'
    review.reviewed_at = export.reviewed_at
    for item in review.decisions:
        item.decision = 'approved'
    final = analyze_course(repo, export.course_id, **args, cluster_review=review)
    return candidate, review, final


def test_handoff_completion_is_explicit_and_strict():
    for value in ('true', 1, [], {}):
        with pytest.raises(ValidationError):
            completion_metadata({'schema_version':'1.0', 'errors_analyzed':value})
    assert completion_metadata({'schema_version':'1.0'})['errors_analyzed'] is None
    assert completion_metadata({'schema_version':'1.0', 'errors_analyzed':False})['errors_analyzed'] is False


def test_twenty_record_handoff_and_manual_error_denominators():
    sdk, repo, export = source()
    batch = repo.load_course(export.course_id)
    records, _, readiness = _adapt(batch, AnalyticsConfig(), None)
    assert len(records) == 20 and readiness.eligible_error_events == 15
    assert sum(r.errors_analyzed is True for r in records) == 17
    assert len(export.approved_inputs(records, batch, live=True)) == 15
    bundle = analyze_course(repo, export.course_id)
    for doc in bundle.documents:
        if doc.scope == 'class_outcome':
            errors = {error.code:error for error in doc.metrics.error_prevalence}
            assert errors['inequality_direction'].numerator == 5
            assert errors['inequality_direction'].denominator == 10
            assert errors['unit_conversion_error'].prevalence == .5


@pytest.mark.parametrize('change', ['revision','error_id','evidence','privacy','course'])
def test_invalid_review_export_rejected(change):
    _, repo, export = source()
    payload = export.model_dump(mode='json')
    if change == 'revision': payload['entries'][0]['ler_revision'] = 99
    if change == 'error_id': payload['entries'][0]['ler_error_id'] = '00000000-0000-0000-0000-000000000099'
    if change == 'evidence': payload['entries'][0]['evidence_ref_ids'] = payload['entries'][-1]['evidence_ref_ids']
    if change == 'privacy': payload['entries'][0]['privacy_reviewed'] = False
    if change == 'course': payload['course_id'] = '00000000-0000-0000-0000-000000000099'
    with pytest.raises(ValueError):
        analyze_course(repo, export.course_id, cluster=True, reviewed_export=payload, embedder=TwoFamilies())


def test_reviewed_clusters_publish_and_readback_with_evidence():
    sdk, repo, export = source()
    candidate, review, final = reviewed_run(repo, export)
    assert candidate.run_id != final.run_id
    with pytest.raises(ValueError, match='requires excerpt and group review'):
        persist_analysis(repo, candidate, exclusive_course_access=True)
    assert not sdk.tables['analytics_runs']
    assert len([d for d in final.documents if d.scope == 'misconception_cluster']) == 2
    persist_analysis(repo, final, exclusive_course_access=True)
    assert persist_analysis(repo, final, exclusive_course_access=True) == 'already_completed'
    dashboard = load_dashboard(sdk, lambda:repo, export.course_id)
    assert len(dashboard.clusters) == 2
    assert all(group.representative_text for group in dashboard.clusters)
    assert sorted(group.unique_students for group in dashboard.clusters) == [5, 5]
    assert {group.error_code for group in dashboard.clusters} == {'inequality_direction','unit_conversion_error'}


def test_pending_or_obsolete_cluster_review_is_rejected():
    _, repo, export = source()
    candidate = analyze_course(repo, export.course_id, cluster=True, reviewed_export=export, embedder=TwoFamilies())
    review = candidate.manifest['cluster_review_template']
    with pytest.raises(ValueError, match='incomplete'):
        analyze_course(repo, export.course_id, cluster=True, reviewed_export=export, cluster_review=review, embedder=TwoFamilies())
    _, review, _ = reviewed_run(repo, export)
    export.entries[0].text += ' Revised wording.'
    with pytest.raises(ValueError, match='renewed review'):
        analyze_course(repo, export.course_id, cluster=True, reviewed_export=export, cluster_review=review, embedder=TwoFamilies())


def test_rejected_groups_are_not_published_and_scores_unchanged():
    _, repo, export = source()
    _, review, final = reviewed_run(repo, export)
    before = {d.id: d.metrics for d in final.documents if d.scope != 'misconception_cluster'}
    for decision in review.decisions: decision.decision = 'rejected'
    rejected = analyze_course(repo, export.course_id, cluster=True, reviewed_export=export, cluster_review=review, embedder=TwoFamilies(), run_id=final.run_id)
    assert all(d.scope != 'misconception_cluster' for d in rejected.documents)
    assert {d.id:d.metrics for d in rejected.documents} == before


def test_ml_readiness_does_not_encode():
    _, repo, export = source()
    batch = repo.load_course(export.course_id)
    records, _, _ = _adapt(batch, AnalyticsConfig(), None)
    class NoInference(TwoFamilies):
        def encode(self, texts): raise AssertionError('preflight must not infer')
    report = ml_readiness(records, export.approved_inputs(records, batch, live=True), embedder=NoInference())
    assert report['status'] == 'ready' and report['accepted_texts'] == 15
    assert ml_readiness(records, [], embedder=NoInference())['status'] == 'not_ready'


def test_missing_error_evidence_is_unknown_not_error_free():
    sdk, repo, export = source()
    sdk.tables['ler_error_evidence']=[]
    batch=repo.load_course(export.course_id)
    assert 'missing_error_evidence' in {issue.code for issue in batch.issues}
    records,_,_= _adapt(batch,AnalyticsConfig(),None)
    assert ml_readiness(records,[])['eligible_error_events']==0


@pytest.mark.parametrize('change',['source','config','model'])
def test_review_cannot_be_reused_after_input_changes(change):
    sdk,repo,export=source()
    _,review,_=reviewed_run(repo,export)
    config=AnalyticsConfig()
    encoder=TwoFamilies()
    if change=='source': sdk.tables['responses'][0]['points_earned']='0'
    if change=='config': config=AnalyticsConfig(clustering_eps=.35)
    if change=='model': encoder.metadata=encoder.metadata.model_copy(update={'revision':'changed'})
    with pytest.raises(ValueError,match='renewed review'):
        analyze_course(repo,export.course_id,cluster=True,reviewed_export=export,cluster_review=review,embedder=encoder,config=config)


def test_private_cluster_report_tamper_cannot_publish():
    sdk,repo,export=source()
    _,_,bundle=reviewed_run(repo,export)
    bundle.clustering_report['input_snapshot']='sha256:'+'0'*64
    with pytest.raises(ValueError,match='frozen inputs'):
        persist_analysis(repo,bundle,exclusive_course_access=True)
    assert not sdk.tables['analytics_runs']


def test_cluster_evidence_endpoint_checks_role_and_freshness(client,monkeypatch):
    from app.main import app
    from app.analytics.access import AnalyticsSession,analytics_session
    from app.routers import analytics
    sdk,repo,export=source()
    uid='00000000-0000-0000-0000-000000099999'
    sdk.tables['enrollments']=[{'user_id':uid,'course_id':str(export.course_id),'role':'instructor'}]
    _,_,bundle=reviewed_run(repo,export)
    persist_analysis(repo,bundle,exclusive_course_access=True)
    doc=next(d for d in bundle.documents if d.scope=='misconception_cluster')
    app.dependency_overrides[analytics_session]=lambda:AnalyticsSession(UUID(uid),sdk)
    monkeypatch.setattr(analytics,'control_repository',lambda:repo)
    path=f'/api/analytics/courses/{export.course_id}/clusters/{doc.id}/evidence'
    response=client.get(path)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert len(response.json()['evidence'])>=5
    assert 'learner_id' not in response.text
    sdk.tables['enrollments'][0]['role']='student'
    assert client.get(path).status_code==403
    sdk.tables['enrollments'][0]['role']='instructor'
    sdk.tables['responses'][0]['points_earned']='0'
    assert client.get(path).status_code==409


def test_tutor_bridge_consumes_fresh_schema_11_and_blocks_stale():
    sdk, repo, export = source()
    bundle = analyze_course(repo, export.course_id)
    persist_analysis(repo, bundle, exclusive_course_access=True)
    path = Path(__file__).resolve().parents[4] / 'carmen-study-guide/mock-canvas/tutor/analytics_bridge.py'
    spec = importlib.util.spec_from_file_location('tested_analytics_bridge', path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    identity = SimpleNamespace(course_id=str(export.course_id), learner_id=sdk.tables['learners'][0]['id'])
    user = Client(sdk.tables, learner_id=identity.learner_id)
    assert len(bridge.weak_outcomes(sdk, user, identity)) == 2
    sdk.tables['responses'][0]['points_earned'] = '0'
    assert bridge.weak_outcomes(sdk, user, identity) == []


@pytest.mark.skipif(not os.environ.get('ANALYTICS_MODEL_CACHE'), reason='real-model cache not configured')
def test_real_cached_model_through_review_and_storage():
    from app.analytics.embeddings import MiniLMOnnxEmbedder
    _, repo, export = source()
    _, _, bundle = reviewed_run(repo, export, MiniLMOnnxEmbedder(Path(os.environ['ANALYTICS_MODEL_CACHE'])))
    assert len([doc for doc in bundle.documents if doc.scope == 'misconception_cluster']) == 2
    assert persist_analysis(repo, bundle, exclusive_course_access=True) == 'completed'
