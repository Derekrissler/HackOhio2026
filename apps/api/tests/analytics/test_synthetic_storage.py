"""Authorized candidate storage never edits source evidence or published ARRs."""
from copy import deepcopy

import pytest

from app.analytics.synthetic_storage import METHOD, archive_row, store_demo_run
from app.analytics.synthetic_workflow import analyze_demo
from .test_clustering import FixtureEmbedder
from .test_source_repairs import RepairClient
from .test_synthetic_workflow import fixture_source, fictional_text_review

AUTH = 'Fictional unit-test authorization, not permission to access a real database.'


def computed():
    source = fixture_source()
    review = fictional_text_review(source)
    bundle, _ = analyze_demo(source, review, FixtureEmbedder())
    return source, review, bundle


def test_requires_explicit_authorization_before_database_access():
    source, review, bundle = computed()
    with pytest.raises(ValueError, match='authorization'):
        store_demo_run(object(), source, review, bundle)


def test_insert_readback_and_idempotent_retry_only_touch_one_run():
    source, review, bundle = computed()
    existing = {'id': '00000000-0000-4000-8000-000000000001', 'course_id': str(bundle.course_id),
                'method': 'real_score_run', 'params': {'status': 'complete'}}
    client = RepairClient({'courses': [{'id': str(bundle.course_id)}], 'analytics_runs': [deepcopy(existing)]})
    result = store_demo_run(client, source, review, bundle,
                            authorize_synthetic_storage=True, authorization_note=AUTH)
    assert result['status'] == 'stored' and result['readback_verified']
    assert result['published_arrs'] == 0 and result['academic_evidence_changed'] is False
    assert client.tables['analytics_runs'][0] == existing
    row = client.tables['analytics_runs'][1]
    assert row['method'] == METHOD and row['params']['status'] == 'demo_candidate'
    assert row['params']['publication_status'] == 'not_published'
    assert row['params']['synthetic_demo_v1']['synthetic_classifications'] is True
    assert all(d['decision'] == 'pending' for d in row['params']['cluster_review_template']['decisions'])
    again = store_demo_run(client, source, review, bundle,
                           authorize_synthetic_storage=True, authorization_note=AUTH)
    assert again['status'] == 'already_stored'
    assert [(table, mode) for table, mode, _, _ in client.calls if mode != 'select'] == [('analytics_runs', 'insert')]


def test_conflicting_existing_run_is_never_overwritten():
    source, review, bundle = computed()
    row = archive_row(source, review, bundle, authorization_note=AUTH)
    row['params']['status'] = 'different_content'
    client = RepairClient({'courses': [{'id': str(bundle.course_id)}], 'analytics_runs': [row]})
    with pytest.raises(ValueError, match='overwrite'):
        store_demo_run(client, source, review, bundle,
                       authorize_synthetic_storage=True, authorization_note=AUTH)
    assert not [call for call in client.calls if call[1] != 'select']


def test_different_text_review_is_rejected_before_database_access():
    source, review, bundle = computed()
    review.decisions[0].decision = 'rejected'
    review.decisions[0].notes = 'Fictional changed review.'
    with pytest.raises(ValueError, match='approved source and text review'):
        store_demo_run(object(), source, review, bundle,
                       authorize_synthetic_storage=True, authorization_note=AUTH)


def test_missing_existing_course_does_not_create_one():
    source, review, bundle = computed()
    client = RepairClient({'courses': [], 'analytics_runs': []})
    with pytest.raises(ValueError, match='no new course'):
        store_demo_run(client, source, review, bundle,
                       authorize_synthetic_storage=True, authorization_note=AUTH)
    assert not [call for call in client.calls if call[1] != 'select']
