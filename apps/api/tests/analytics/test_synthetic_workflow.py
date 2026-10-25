"""Review-gated synthetic analytics: only fictional decisions and local models."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analytics.cluster_review import ClusterReview
from app.analytics.provenance import content_hash
from app.analytics.service import AnalysisBundle, persist_analysis
from app.analytics.synthetic_inputs import generate_dataset
from app.analytics.synthetic_source import SyntheticDemoSource
from app.analytics.synthetic_workflow import (DemoTextReview, DemoGroupReview, GroupAssessment,
    analyze_demo, cluster_review_packet, compile_text_review, finalize_demo, text_review_packet,
    text_review_markdown, validation_report, review_attention)
from .test_synthetic_inputs import demo_snapshot
from .test_clustering import FixtureEmbedder

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def fixture_source():
    _, snapshot = demo_snapshot()
    return SyntheticDemoSource(snapshot, generate_dataset(snapshot))


def fictional_text_review(source):
    review = DemoTextReview.model_validate(text_review_packet(source)['review'])
    review.reviewer_kind = 'human'
    review.reviewer_ref = 'fictional-unit-test-reviewer'
    review.reviewed_at = NOW
    for decision in review.decisions:
        decision.decision = 'approved'
        decision.privacy_reviewed = decision.context_reviewed = decision.synthetic_label_verified = True
        decision.notes = 'Fictional test approval only; not a real course review.'
    return DemoTextReview.model_validate_json(review.model_dump_json())


def fictional_group_review(candidate, *, decision='approved'):
    packet = cluster_review_packet(candidate)
    review = ClusterReview.model_validate(packet['review'])
    review.reviewer_ref = 'fictional-unit-test-reviewer'
    review.reviewed_at = NOW
    for row in review.decisions:
        row.decision = decision
    return DemoGroupReview(provenance=packet['provenance'], candidate_bundle_hash=candidate.bundle_hash(),
        reviewer_kind='human', review=review,
        assessments=[GroupAssessment(group_key=d.group_key, notes='Fictional unit-test interpretation.') for d in review.decisions])


def test_validation_report_and_readable_pending_packet():
    source = fixture_source()
    report = validation_report(source)
    assert len(report['checks']) == 13 and set(report['checks'].values()) == {'passed'}
    assert report['score_signature_unchanged'] and report['insufficient_lers_preserved'] == 1
    packet = text_review_packet(source)
    assert all(d['decision'] == 'pending' for d in packet['review']['decisions'])
    markdown = text_review_markdown(packet)
    assert 'not observed learner mistakes' in markdown
    assert str(source.dataset.excerpt_candidates[0].ler_error_id) in markdown
    assert packet['contexts'][0]['question_text'] in markdown


def test_pending_or_missing_review_attestations_prevent_export_and_inference():
    source = fixture_source()
    pending = DemoTextReview.model_validate(text_review_packet(source)['review'])
    class NeverEncode:
        def encode(self, texts):
            pytest.fail('pending descriptions must not reach a model')
    with pytest.raises(ValueError, match='incomplete'):
        analyze_demo(source, pending, NeverEncode())
    approved = fictional_text_review(source).model_dump(mode='json')
    approved['decisions'][0]['privacy_reviewed'] = False
    with pytest.raises(ValueError, match='attestations'):
        DemoTextReview.model_validate(approved)


@pytest.mark.parametrize('change', ['binding', 'missing', 'duplicate', 'delegation'])
def test_review_binding_completeness_and_attribution(change):
    source = fixture_source()
    fields = fictional_text_review(source).model_dump(mode='json')
    if change == 'binding': fields['binding'] = 'changed'
    if change == 'missing': fields['decisions'].pop()
    if change == 'duplicate': fields['decisions'].append(deepcopy(fields['decisions'][0]))
    if change == 'delegation': fields['reviewer_kind'] = 'delegated_agent'
    with pytest.raises(ValueError):
        compile_text_review(source, DemoTextReview.model_validate(fields))


def test_rejected_description_does_not_enter_export():
    source = fixture_source()
    review = fictional_text_review(source)
    rejected = review.decisions[0]
    rejected.decision = 'rejected'
    rejected.notes = 'Fictional test rejects a context mismatch.'
    export = compile_text_review(source, review)
    assert rejected.ler_error_id not in {e.ler_error_id for e in export.entries}
    assert len(export.entries) == len(review.decisions) - 1
    assert export.reviewer_ref.startswith('human:')


def test_real_clustering_engine_with_fixture_vectors_through_review_and_arrs():
    source = fixture_source()
    review = fictional_text_review(source)
    candidate, export = analyze_demo(source, review, FixtureEmbedder())
    packet = cluster_review_packet(candidate)
    assert packet['groups'] and len(export.entries) > 0
    assert all(d['decision'] == 'pending' for d in packet['review']['decisions'])
    group_review = fictional_group_review(candidate)
    final, summary = finalize_demo(source, review, candidate, group_review, FixtureEmbedder())
    assert summary['status'] == 'finalized_local_demo'
    assert summary['cluster_arrs'] > 0 and not summary['database_writes']
    assert final.run_id != candidate.run_id
    assert all(d.provenance['synthetic_demo_v1'] == source.dataset.provenance() for d in final.documents)
    with pytest.raises(ValueError, match='cannot be published'):
        persist_analysis(object(), final, exclusive_course_access=True)


def test_rejected_group_is_not_a_final_arr():
    source = fixture_source()
    review = fictional_text_review(source)
    candidate, _ = analyze_demo(source, review, FixtureEmbedder())
    rejected = fictional_group_review(candidate, decision='rejected')
    final, summary = finalize_demo(source, review, candidate, rejected, FixtureEmbedder())
    assert not [d for d in final.documents if d.scope == 'misconception_cluster']
    assert summary['approved_groups'] == 0


def test_candidate_tampering_and_stale_group_reviews_fail():
    source = fixture_source()
    review = fictional_text_review(source)
    candidate, _ = analyze_demo(source, review, FixtureEmbedder())
    group_review = fictional_group_review(candidate)
    group_review.candidate_bundle_hash = 'changed'
    with pytest.raises(ValueError, match='different demo'):
        finalize_demo(source, review, candidate, group_review, FixtureEmbedder())
    candidate.clustering_report['input_snapshot'] = 'changed'
    with pytest.raises(ValueError, match='frozen inputs'):
        cluster_review_packet(candidate)


def test_validation_cli_does_not_overwrite_human_decisions(tmp_path, monkeypatch, capsys):
    from app.analytics import synthetic_source
    from app.analytics.cli import main
    import json
    monkeypatch.setattr(synthetic_source, 'PRIVATE_ROOT', tmp_path)
    source = fixture_source()
    snapshot = synthetic_source.write_private(tmp_path / 'snapshot.json', source.snapshot)
    dataset = synthetic_source.write_private(tmp_path / 'dataset.json', source.dataset)
    args = ['demo', 'validate', '--snapshot', str(snapshot), '--dataset', str(dataset)]
    assert main(args) == 0
    output = json.loads(capsys.readouterr().out)
    path = Path(output['decisions'])
    decisions = fictional_text_review(source)
    path.write_text(decisions.model_dump_json(), encoding='utf-8')
    before = path.read_bytes()
    assert main(args) == 0
    capsys.readouterr()
    assert path.read_bytes() == before


def test_cli_rejects_pending_decisions_before_loading_cached_model(tmp_path, monkeypatch, capsys):
    from app.analytics import synthetic_source, embeddings
    from app.analytics.cli import main
    monkeypatch.setattr(synthetic_source, 'PRIVATE_ROOT', tmp_path)
    source = fixture_source()
    snapshot = synthetic_source.write_private(tmp_path / 'snapshot.json', source.snapshot)
    dataset = synthetic_source.write_private(tmp_path / 'dataset.json', source.dataset)
    review = synthetic_source.write_private(tmp_path / 'review.json', text_review_packet(source)['review'])
    def forbidden(*args, **kwargs):
        pytest.fail('pending decisions must be rejected before constructing an embedder')
    monkeypatch.setattr(embeddings, 'MiniLMOnnxEmbedder', forbidden)
    assert main(['demo', 'analyze', '--snapshot', str(snapshot), '--dataset', str(dataset),
                 '--review', str(review), '--model-cache', str(tmp_path / 'not-a-model')]) == 1
    assert 'invalid_input_or_unavailable_configuration' in capsys.readouterr().out


def test_context_advisory_leaves_review_decision_pending():
    source = fixture_source()
    packet = text_review_packet(source)
    packet['contexts'][0]['candidate']['error_code'] = 'missing_edge_case_tests'
    packet['contexts'][0]['question_text'] = 'In test-first prompting, you should:'
    attention = review_attention(packet)
    assert attention['advisory_count'] == 1
    assert attention['flags'][0]['decision'] == 'pending'
    assert attention['automated_decisions'] is False
