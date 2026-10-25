"""Offline synthetic overlay integration; no live credentials or model inference."""
from copy import deepcopy
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.analytics.config import AnalyticsConfig
from app.analytics.evidence_repository import assemble_evidence_batch
from app.analytics.provenance import content_hash
from app.analytics.reviewed_excerpts import ReviewedExcerptExport
from app.analytics.service import AnalysisBundle, _adapt, analyze_course, persist_analysis
from app.analytics.synthetic_inputs import (DemoSourceSnapshot, ExcerptCandidate, MARKER, SyntheticDataset,
    SyntheticGenerationConfig, VIBE_COURSE, generate_dataset)
from app.analytics.synthetic_source import SyntheticDemoSource, capture_snapshot, preview_report, private_path
from .test_error_integration import source as fictional_source


def demo_snapshot():
    sdk, _, export = fictional_source()
    sdk.tables = json.loads(json.dumps(sdk.tables).replace(str(export.course_id), str(VIBE_COURSE)))
    sdk.tables['ler_errors'] = []
    sdk.tables['ler_error_evidence'] = []
    for ler in sdk.tables['lers']:
        ler['payload'].pop('analytics_v1', None)
    for row in sdk.tables['questions']:
        row['text'] = 'Build a command-line to-do app in Python using an AI assistant.'
    for row in sdk.tables['outcomes']:
        row['code'] = 'LO-02'
    for table in ('feedback', 'resource_chunks', 'chunk_outcomes', 'error_taxonomy'):
        sdk.tables[table] = []
    return sdk, capture_snapshot(sdk)


def test_capture_is_read_only_and_reuses_exact_live_assembly():
    sdk, snapshot = demo_snapshot()
    assert all(mode == 'select' for _, mode, _, _ in sdk.calls)
    assert snapshot.base_batch.fingerprint() == assemble_evidence_batch(VIBE_COURSE,
        snapshot.base_batch.source_manifest).fingerprint()
    assert len(snapshot.base_batch.envelopes) == 20


def test_determinism_source_preservation_and_pending_reviews():
    _, snapshot = demo_snapshot()
    original = snapshot.model_dump_json()
    first = generate_dataset(snapshot)
    second = generate_dataset(snapshot, generated_at='2026-11-01T12:00:00Z')
    assert first.dataset_id == second.dataset_id
    assert first.content_digest == second.content_digest
    assert first.classifications == second.classifications
    assert first.evidence == second.evidence
    assert first.content_digest != generate_dataset(snapshot, SyntheticGenerationConfig(seed=42)).content_digest
    report = preview_report(snapshot, first)
    assert report['score_signature_unchanged'] and report['original_source_fields_unchanged']
    assert report['insufficient_lers_preserved'] == 1
    assert report['approved_text_reviews'] == 0 and report['pending_text_reviews'] > 0
    assert report['shortfall'] > 0  # Never manufacture unrelated records to meet the target.
    assert all(c.decision == 'pending' and c.privacy_reviewed is False for c in first.excerpt_candidates)
    assert snapshot.model_dump_json() == original
    assert not report['ml_executed'] and not report['database_writes']


def test_synthetic_evidence_is_separate_from_original_feedback():
    _, snapshot = demo_snapshot()
    dataset = generate_dataset(snapshot)
    batch = SyntheticDemoSource(snapshot, dataset).load_course(VIBE_COURSE)
    old_refs = {r['id'] for r in snapshot.base_batch.source_manifest['evidence_refs']}
    for evidence in dataset.evidence:
        assert str(evidence.id) not in old_refs
        assert evidence.source_type == 'manual' and evidence.synthetic
        assert evidence.page is None and evidence.document_id is None
        assert 'SYNTHETIC DEMONSTRATION' in evidence.excerpt
        assert evidence.canvas_ref.startswith('synthetic-demo://')
    assert all(e['instructor_status'] == 'unreviewed' for e in batch.source_manifest['ler_errors'])
    assert 'feedback' not in batch.source_manifest
    records, _, _ = _adapt(batch, AnalyticsConfig(), None)
    for record in records:
        for error in record.errors:
            assert set(error.evidence_ref_ids) <= set(record.evidence_ref_ids)
            assert set(error.outcome_ids) <= {m.outcome_id for m in record.outcome_mappings}


@pytest.mark.parametrize('change', ['text', 'grade', 'learner', 'error_id', 'outcome', 'evidence', 'missing_marker'])
def test_changed_private_artifacts_are_rejected_even_if_content_digest_is_recomputed(change):
    _, snapshot = demo_snapshot()
    dataset = generate_dataset(snapshot)
    if change == 'grade':
        payload = snapshot.model_dump(mode='json')
        payload['base_batch']['source_manifest']['responses'][0]['points_earned'] = 999
        with pytest.raises(ValueError):
            DemoSourceSnapshot.model_validate(payload)
        return
    payload = dataset.model_dump(mode='json')
    case = next(c for c in payload['classifications'] if c['errors'])
    if change == 'text': case['errors'][0]['description'] = 'Changed hypothetical text.'
    if change == 'learner': case['learner_id'] = '00000000-0000-4000-8000-000000000099'
    if change == 'error_id': case['errors'][0]['id'] = '00000000-0000-4000-8000-000000000099'
    if change == 'outcome': case['errors'][0]['outcome_ids'] = ['00000000-0000-4000-8000-000000000099']
    if change == 'evidence': case['errors'][0]['evidence_ref_ids'] = ['00000000-0000-4000-8000-000000000099']
    if change == 'missing_marker':
        payload.pop('dataset_kind')
        # Required demo marker must be explicit, not filled back from a default.
        with pytest.raises(ValueError):
            SyntheticDataset.model_validate(payload)
        return
    payload['content_digest'] = content_hash({k: v for k, v in payload.items() if k not in ('generated_at', 'content_digest')})
    changed = SyntheticDataset.model_validate(payload)
    with pytest.raises(ValueError, match='reproduce'):
        SyntheticDemoSource(snapshot, changed).load_course(VIBE_COURSE)


def test_provenance_reaches_every_arr_and_publication_is_rejected_before_repository_access():
    _, snapshot = demo_snapshot()
    source = SyntheticDemoSource(snapshot, generate_dataset(snapshot))
    # Statistical plumbing only; phase 3 does not execute ML or approve text.
    bundle = analyze_course(source, VIBE_COURSE)
    assert bundle.source_kind == 'offline_fixture'
    assert bundle.manifest[MARKER] == source.dataset.provenance()
    assert bundle.documents and all(d.provenance[MARKER] == bundle.manifest[MARKER] for d in bundle.documents)
    with pytest.raises(ValueError, match='cannot be published'):
        persist_analysis(object(), bundle, exclusive_course_access=True)
    bad = bundle.model_dump(mode='json')
    bad['documents'][0]['provenance'].pop(MARKER)
    with pytest.raises(ValueError, match='provenance mismatch'):
        AnalysisBundle.model_validate(bad)


def test_candidate_cannot_assert_an_approval():
    _, snapshot = demo_snapshot()
    candidate = generate_dataset(snapshot).excerpt_candidates[0].model_dump(mode='json')
    candidate['decision'] = 'approved'
    candidate['privacy_reviewed'] = True
    with pytest.raises(ValidationError):
        ExcerptCandidate.model_validate(candidate)


def test_strict_offline_review_checks_exact_error_identity():
    _, snapshot = demo_snapshot()
    dataset = generate_dataset(snapshot)
    source = SyntheticDemoSource(snapshot, dataset)
    batch = source.load_course(VIBE_COURSE)
    records, _, _ = _adapt(batch, AnalyticsConfig(), None)
    candidate = dataset.excerpt_candidates[0]
    # An attributed fictional review is test input only, never an approval of live/demo data.
    entry = candidate.model_dump(mode='json', exclude={'decision','privacy_reviewed','context_reviewed','reviewer_ref','reviewed_at'})
    entry['privacy_reviewed'] = True
    entry['ler_error_id'] = '00000000-0000-4000-8000-000000000099'
    export = ReviewedExcerptExport(schema_version='1.0', course_id=VIBE_COURSE, extraction_version='fictional-test',
        reviewer_ref='fictional-test-reviewer', reviewed_at='2026-10-25T00:00:00Z', review_revision='test', entries=[entry])
    with pytest.raises(ValueError, match='different error'):
        export.approved_inputs(records, batch, verify_source_rows=True)


def test_capture_detects_concurrent_context_edits():
    sdk, _ = demo_snapshot()
    counter = [0]
    def change(query):
        if query.table == 'feedback':
            counter[0] += 1
            if counter[0] == 1:
                sdk.tables['questions'][0]['text'] += ' changed'
    sdk.after_query = change
    with pytest.raises(ValueError, match='changed|differs'):
        capture_snapshot(sdk)


def test_artifacts_cannot_escape_private_directory():
    with pytest.raises(ValueError, match='private'):
        private_path('public-demo.json')


def test_simulated_completion_states_do_not_change_semantic_status():
    _, snapshot = demo_snapshot()
    config = SyntheticGenerationConfig(target_error_lers=4, no_error_cases=1, not_completed_cases=1, ambiguous_cases=1)
    dataset = generate_dataset(snapshot, config)
    batch = SyntheticDemoSource(snapshot, dataset).load_course(VIBE_COURSE)
    envelopes = {row['ler']['id']: row for row in batch.envelopes}
    originals = {row['ler']['id']: row for row in snapshot.base_batch.envelopes}
    expected = {'completed_with_errors': True, 'completed_no_errors': True,
                'not_completed': False, 'ambiguous': None}
    assert set(c.state for c in dataset.classifications) == set(expected)
    for case in dataset.classifications:
        row = envelopes[str(case.ler_id)]
        assert row['errors_analyzed'] is expected[case.state]
        assert row['ler']['analysis_status'] == originals[str(case.ler_id)]['ler']['analysis_status']


@pytest.mark.parametrize('change', ['missing_course', 'orphan_response'])
def test_complete_offline_source_enforces_database_relationships(change):
    _, snapshot = demo_snapshot()
    payload = snapshot.model_dump(mode='json')
    response = payload['base_batch']['source_manifest']['responses'][0]
    if change == 'missing_course': response.pop('course_id')
    else: response['question_id'] = '00000000-0000-4000-8000-000000000099'
    payload['snapshot_digest'] = content_hash({'base_batch': payload['base_batch'], 'context': payload['context']})
    with pytest.raises(ValueError, match='manifest|source row'):
        DemoSourceSnapshot.model_validate(payload)


def test_cli_generation_retry_keeps_identical_private_artifacts(tmp_path, monkeypatch, capsys):
    from app.analytics import synthetic_source
    from app.analytics.cli import main
    _, snapshot = demo_snapshot()
    monkeypatch.setattr(synthetic_source, 'PRIVATE_ROOT', tmp_path)
    snapshot_path = synthetic_source.write_private(tmp_path / 'source.json', snapshot)
    args = ['demo', 'generate', '--snapshot', str(snapshot_path), '--target', '4']
    assert main(args) == 0
    first_output = json.loads(capsys.readouterr().out)
    folder = synthetic_source.Path(first_output['private_directory'])
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert main(args) == 0
    second_output = json.loads(capsys.readouterr().out)
    assert first_output == second_output
    assert before == {p.name: p.read_bytes() for p in folder.iterdir()}
    assert 'fictional private answer' not in json.dumps(second_output)
