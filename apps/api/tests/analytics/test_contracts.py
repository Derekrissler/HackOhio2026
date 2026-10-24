"""Boundary tests only; numerical aggregation is implemented in later phases."""

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.analytics.config import AnalyticsConfig
from app.analytics.contracts import ARR_ADAPTER, PerformanceMetrics, RunMetadata
from app.analytics.ler_adapter import adapt_ler


def fixture():
    return json.loads((Path(__file__).parent / "fixtures" / "ler.json").read_text())


def test_preserves_points_weights_and_evidence_without_normalizing_yet():
    result = adapt_ler(fixture())
    assert result.issues == []
    record = result.record
    assert record.points_earned == 6
    assert record.points_possible == 10
    assert [m.weight for m in record.outcome_mappings] == [3, 1]
    assert record.evidence_ref_ids == [UUID("00000000-0000-4000-8000-000000000010")]
    assert "response_text" not in record.model_dump()


@pytest.mark.parametrize("value", [None, 0, -1, "NaN", "Infinity", True, "bad"])
def test_bad_denominator_never_becomes_zero(value):
    data = fixture()
    data["question"]["points_possible"] = value
    result = adapt_ler(data)
    assert result.record is not None
    assert result.record.points_possible is None
    assert any(i.field == "points_possible" for i in result.issues)


@pytest.mark.parametrize("value", [None, -1, "NaN", True, 11])
def test_bad_earned_score_preserves_qualitative_evidence(value):
    data = fixture()
    data["response"]["points_earned"] = value
    result = adapt_ler(data)
    assert result.record.points_earned is None
    assert result.record.errors[0].code == "inequality_direction"


@pytest.mark.parametrize("timestamp", [None, "bad", "2026-10-24T15:00:00"])
def test_missing_invalid_and_naive_timestamps_flagged(timestamp):
    data = fixture()
    data["attempt"]["submitted_at"] = timestamp
    result = adapt_ler(data)
    assert result.record.observed_at is None
    assert any(i.field == "observed_at" for i in result.issues)


def test_unknown_assistance_is_not_independent():
    data = fixture()
    data["ler"].pop("assistance_level")
    assert adapt_ler(data).record.assistance == "unknown"


def test_hints_conflict_with_independence():
    data = fixture()
    data["ler"]["hints_used"] = 2
    assert adapt_ler(data).record is None


def test_superseded_and_insufficient_records_are_explicit():
    data = fixture()
    data["ler"].update(is_current=False, analysis_status="insufficient")
    result = adapt_ler(data)
    assert {i.code for i in result.issues} == {"superseded_ler", "insufficient_analysis"}


def test_join_mismatch_quarantined():
    data = fixture()
    data["response"]["learner_id"] = "00000000-0000-4000-8000-000000000099"
    assert adapt_ler(data).record is None


@pytest.mark.parametrize("weight", [-1, "NaN"])
def test_invalid_weights_rejected(weight):
    data = fixture()
    data["outcome_mappings"][0]["weight"] = weight
    assert adapt_ler(data).record is None


def test_duplicate_mapping_rejected():
    data = fixture()
    data["outcome_mappings"].append(data["outcome_mappings"][0])
    assert adapt_ler(data).record is None


def test_validation_errors_do_not_echo_sensitive_values():
    data = fixture()
    data["ler"]["learner_id"] = "Private Student Name"
    assert "Private Student Name" not in adapt_ler(data).model_dump_json()


def arr(scope="student_outcome"):
    data = fixture()
    lid = data["ler"]["id"]
    return {
        "id": lid, "run_id": lid, "course_id": data["ler"]["course_id"],
        "scope": scope, "subject_learner_id": data["ler"]["learner_id"],
        "outcome_id": data["outcome_mappings"][0]["outcome_id"],
        "evidence_ler_ids": [lid], "evidence_sets": {"score_ler_ids": [lid]},
        "inclusion_rule": "latest independent eligible attempt",
        "numerator_definition": "weighted earned points",
        "denominator_definition": "weighted possible points",
        "created_at": "2026-10-24T16:00:00Z",
        "interpretation_limits": {"insufficient_evidence": True, "incomplete_coverage": True},
        "metrics": {"observed_score_ratio": None, "weighted_earned": 6,
                    "weighted_possible": 10, "scored_observation_count": 1,
                    "distinct_question_count": 1, "distinct_assessment_count": 1},
    }


def test_arr_roundtrip_and_mastery_null():
    record = ARR_ADAPTER.validate_python(arr())
    assert record.metrics.mastery_estimate is None
    assert ARR_ADAPTER.validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("field", ["subject_learner_id", "outcome_id"])
def test_student_scope_required_fields(field):
    data = arr()
    del data[field]
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


def test_evidence_counts_cannot_hide_unlinked_metric_evidence():
    data = arr()
    data["evidence_ler_ids"] = []
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


def test_nonnull_mastery_rejected():
    data = arr()
    data["metrics"]["mastery_estimate"] = 0.8
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


def test_policy_invalid_threshold_and_unknown_options():
    with pytest.raises(ValidationError):
        AnalyticsConfig(observed_performance_threshold=1.2)
    with pytest.raises(ValidationError):
        AnalyticsConfig(predictive_mastery=True)


def test_ratio_requires_denominator():
    data = arr()["metrics"]
    data.update(observed_score_ratio=0.5, weighted_earned=0, weighted_possible=0)
    with pytest.raises(ValidationError):
        PerformanceMetrics.model_validate(data)


@pytest.mark.parametrize("scope", ["class_outcome", "assessment_question"])
def test_aggregate_scopes_roundtrip(scope):
    data = arr(scope)
    del data["subject_learner_id"]
    if scope == "assessment_question":
        del data["outcome_id"]
        data["assessment_id"] = fixture()["ler"]["assessment_id"]
        data["question_id"] = fixture()["ler"]["question_id"]
    data["metrics"] = {
        "assessed_student_count": 1, "valid_student_count": 1,
        "mean_student_ratio": None, "pooled_score_ratio": None,
        "at_or_above_threshold_count": None, "below_threshold_count": None,
    }
    record = ARR_ADAPTER.validate_python(data)
    assert ARR_ADAPTER.validate_json(record.model_dump_json()) == record
    data["subject_learner_id"] = fixture()["ler"]["learner_id"]
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


def test_cluster_contract_preserves_members_without_exposing_excerpts():
    data = arr("misconception_cluster")
    del data["subject_learner_id"], data["outcome_id"]
    members = data["evidence_ler_ids"]
    data["evidence_sets"] = {"cluster_ler_ids": members}
    data["metrics"] = {
        "cluster_id": "cluster-0", "observation_count": 1, "unique_student_count": 1,
        "distinct_question_count": 1, "outcome_ids": [],
        "representative_evidence_ref_ids": fixture()["evidence_ref_ids"],
        "member_ler_ids": members, "embedding_model": "fixture-only",
        "embedding_revision": "fictional-version", "algorithm": "dbscan_cosine",
        "parameters": {"eps": 0.25, "min_samples": 3},
    }
    record = ARR_ADAPTER.validate_python(data)
    assert ARR_ADAPTER.validate_json(record.model_dump_json()) == record
    data["metrics"]["member_ler_ids"] = []
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


def test_descriptive_trend_contract():
    data = arr("longitudinal_trend")
    del data["subject_learner_id"]
    data["evidence_sets"] = {"trend_ler_ids": data["evidence_ler_ids"]}
    data["metrics"] = {
        "earlier_period": {"start": "2026-10-01T00:00:00Z", "end": "2026-10-10T00:00:00Z"},
        "later_period": {"start": "2026-10-10T00:00:00Z", "end": "2026-10-20T00:00:00Z"},
        "earlier_ratio": 0.4, "later_ratio": 0.6, "descriptive_change": 0.2,
    }
    assert ARR_ADAPTER.validate_python(data).metrics.descriptive_change == 0.2
    data["metrics"]["descriptive_change"] = 0.5
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


@pytest.mark.parametrize("origin", ["instructor_practice", "generated_practice"])
def test_practice_has_own_identity_and_timestamp(origin):
    data = fixture()
    data["ler"].update(assessment_origin=origin, practice_attempt_id=data["ler"]["id"],
                       assistance_level="assisted", hints_used=2)
    for key in ("assessment_id", "question_id", "attempt_id", "response_id"):
        del data["ler"][key]
    for key in ("assessment", "question", "attempt", "response"):
        data.pop(key)
    data["practice"] = {"id": data["ler"]["id"], "created_at": "2026-10-24T14:00:00Z"}
    result = adapt_ler(data)
    assert result.record.practice_attempt_id is not None
    assert result.record.assistance == "assisted"
    assert result.record.observed_at.hour == 14


def test_error_analysis_unavailable_is_distinct_from_no_errors():
    data = fixture()
    data["errors"] = []
    data["errors_analyzed"] = None
    assert adapt_ler(data).record.errors_analyzed is None
    data["errors_analyzed"] = True
    assert adapt_ler(data).record.errors_analyzed is True


def test_run_configuration_and_snapshot_roundtrip():
    lid = fixture()["ler"]["id"]
    run = RunMetadata(
        id=lid, course_id=fixture()["ler"]["course_id"], method="weighted_outcome",
        model_version="0.1", input_snapshot="sha256:" + "a" * 64,
        params=AnalyticsConfig(), started_at="2026-10-24T15:00:00Z",
        computed_at="2026-10-24T16:00:00Z",
    )
    assert RunMetadata.model_validate_json(run.model_dump_json()) == run
    assert adapt_ler(fixture()).model_dump_json() == adapt_ler(fixture()).model_dump_json()


def test_score_count_must_match_evidence():
    data = arr()
    data["metrics"]["scored_observation_count"] = 5
    with pytest.raises(ValidationError):
        ARR_ADAPTER.validate_python(data)


def test_missing_required_identity_quarantines():
    data = fixture()
    del data["ler"]["attempt_id"]
    assert adapt_ler(data).record is None


@pytest.mark.parametrize("data", [None, [], {"ler": []}, {"response": "private text"}])
def test_malformed_envelope_is_reported_without_crashing(data):
    result = adapt_ler(data)
    assert result.record is None
    assert result.issues[0].code == "invalid_object"
