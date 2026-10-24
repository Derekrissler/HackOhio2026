from copy import deepcopy
from decimal import Decimal
from uuid import UUID

import pandas as pd
import pytest

from app.analytics.config import AnalyticsConfig
from app.analytics.contracts import AnalysisPeriod
from app.analytics.features import build_features
from app.analytics.ler_adapter import adapt_ler
from .test_contracts import fixture


def uid(number):
    return str(UUID(int=number))


def record(number=101, attempt=1, when="2026-10-24T15:00:00Z", earned=6, possible=10):
    data = fixture()
    data["ler"].update(id=uid(number), attempt_id=uid(1000 + attempt), response_id=uid(2000 + number))
    data["attempt"].update(id=uid(1000 + attempt), attempt_number=attempt, submitted_at=when)
    data["response"].update(id=uid(2000 + number), points_earned=earned)
    data["question"]["points_possible"] = possible
    result = adapt_ler(data)
    assert result.record is not None
    return result.record


def primary_ids(tables):
    return tables.observations.loc[tables.observations.primary_score, "ler_id"].tolist()


def test_manually_verified_score_and_weighted_points():
    tables = build_features([record()])
    assert tables.observations.iloc[0].score_ratio == pytest.approx(0.6)
    assert tables.outcomes.normalized_weight.tolist() == [0.75, 0.25]
    assert tables.outcomes.weighted_earned.tolist() == [4.5, 1.5]
    assert tables.outcomes.weighted_possible.tolist() == [7.5, 2.5]


def test_latest_valid_attempt_keeps_history():
    older = record()
    latest = record(102, 2, "2026-10-25T15:00:00Z", earned=8)
    tables = build_features([latest, older])
    assert len(tables.observations) == 2
    assert primary_ids(tables) == [str(latest.ler_id)]
    assert tables.observations.score_ratio.tolist() == [0.6, 0.8]


def test_invalid_latest_score_does_not_replace_valid_score_but_can_supply_errors():
    older = record()
    latest = record(102, 2, "2026-10-25T15:00:00Z", possible=0)
    tables = build_features([older, latest])
    assert primary_ids(tables) == [str(older.ler_id)]
    assert tables.errors.loc[tables.errors.primary_error, "ler_id"].tolist() == [str(latest.ler_id)]
    assert pd.isna(tables.observations.iloc[1].score_ratio)


def test_identical_id_and_semantic_duplicates_do_not_inflate_evidence():
    first = record()
    duplicate = first.model_copy(update={"ler_id": UUID(uid(103))})
    tables = build_features([first, deepcopy(first), duplicate])
    assert len(tables.observations) == 1
    assert len(tables.errors) == 1
    assert set(tables.exclusions.reason) == {"duplicate_ler_collapsed", "duplicate_question_attempt"}


def test_conflicting_duplicate_id_quarantines_all_versions():
    first = record()
    changed = first.model_copy(update={"points_earned": Decimal(9)})
    tables = build_features([changed, first])
    assert tables.observations.empty
    assert tables.exclusions.reason.tolist() == ["conflicting_ler_id"]


def test_conflicting_question_attempt_quarantines_all_versions():
    first = record()
    changed = first.model_copy(update={"ler_id": UUID(uid(104)), "points_earned": Decimal(9)})
    assert build_features([first, changed]).observations.empty


@pytest.mark.parametrize("updates,reason", [
    ({"is_current": False}, "superseded_ler"),
    ({"analysis_status": "insufficient"}, "insufficient_analysis"),
])
def test_ineligible_lers_excluded_from_every_metric(updates, reason):
    tables = build_features([record().model_copy(update=updates)])
    assert tables.observations.empty and tables.errors.empty and tables.practice.empty
    assert tables.exclusions.reason.tolist() == [reason]


def test_duplicate_error_tags_merge_refs_and_explicit_outcomes():
    first = record()
    error = first.errors[0]
    second = error.model_copy(update={"outcome_ids": [first.outcome_mappings[0].outcome_id]})
    tables = build_features([first.model_copy(update={"errors": [error, second, error]})])
    assert len(tables.errors) == 1
    assert tables.errors.iloc[0].outcome_ids == [str(first.outcome_mappings[0].outcome_id)]
    assert tables.errors.iloc[0].evidence_ref_ids == list(map(str, error.evidence_ref_ids))


def test_rejected_and_configurably_unreviewed_errors_filtered():
    first = record()
    rejected = first.errors[0].model_copy(update={"instructor_status": "rejected"})
    assert build_features([first.model_copy(update={"errors": [rejected]})]).errors.empty
    unreviewed = rejected.model_copy(update={"instructor_status": "unreviewed"})
    current = first.model_copy(update={"errors": [unreviewed]})
    assert len(build_features([current]).errors) == 1
    assert build_features([current], AnalyticsConfig(include_unreviewed_errors=False)).errors.empty


def test_incomplete_error_analysis_never_creates_error_events():
    tables = build_features([record().model_copy(update={"errors_analyzed": None})])
    assert tables.errors.empty
    assert not tables.observations.iloc[0].primary_error


@pytest.mark.parametrize("assistance", ["assisted", "unknown"])
def test_assisted_or_unknown_assessment_does_not_enter_primary(assistance):
    tables = build_features([record().model_copy(update={"assistance": assistance})])
    assert not tables.observations.iloc[0].primary_score
    assert not tables.observations.iloc[0].primary_error


def test_practice_independent_assisted_and_unknown_are_separate():
    records = []
    for index, assistance in enumerate(("independent", "assisted", "unknown")):
        records.append(record(110 + index).model_copy(update={
            "assessment_origin": "generated_practice", "practice_attempt_id": UUID(uid(500 + index)),
            "assistance": assistance, "hints_used": 2 if assistance == "assisted" else None,
        }))
    tables = build_features(records)
    assert len(tables.practice) == 3
    assert tables.practice.assistance.tolist() == ["independent", "assisted", "unknown"]
    assert tables.observations.primary_score.tolist() == [False, False, False]
    assert tables.outcomes.primary_score.tolist() == [False] * 6


def test_zero_weights_ignored_and_no_positive_weights_flagged():
    first = record()
    mappings = [m.model_copy(update={"weight": Decimal(0)}) for m in first.outcome_mappings]
    tables = build_features([first.model_copy(update={"outcome_mappings": mappings})])
    assert tables.outcomes.empty
    assert "no_positive_outcome_weights" in tables.exclusions.reason.tolist()


def test_missing_scores_preserve_unscored_error_history():
    tables = build_features([record(earned=None, possible=None)])
    assert not tables.observations.iloc[0].score_eligible
    assert tables.observations.iloc[0].primary_error
    assert len(tables.errors) == 1
    assert tables.outcomes.weighted_possible.isna().all()


def test_attempt_number_orders_when_timestamps_missing():
    first = record(when=None)
    second = record(102, 2, when=None)
    assert primary_ids(build_features([first, second])) == [str(second.ler_id)]


def test_unresolved_attempt_order_excludes_primary_but_preserves_history():
    first = record(when=None).model_copy(update={"attempt_number": None})
    second = record(102, 2)
    tables = build_features([first, second])
    assert primary_ids(tables) == []
    assert len(tables.observations) == 2
    assert set(tables.exclusions.reason) == {"ambiguous_attempt_order"}


def test_whole_and_parts_never_both_contribute_primary_points():
    part = record()
    whole = record(102).model_copy(update={
        "question_id": UUID(uid(900)), "question_type": "assignment_level",
    })
    tables = build_features([whole, part])
    assert primary_ids(tables) == [str(part.ler_id)]
    assert len(tables.observations) == 2
    assert "whole_assessment_overlaps_parts" in tables.exclusions.reason.tolist()


def test_analysis_window_is_half_open_and_requires_timestamp():
    period = AnalysisPeriod(start="2026-10-24T00:00:00Z", end="2026-10-25T00:00:00Z")
    records = [record(), record(102, 2, "2026-10-25T00:00:00Z"), record(103, 3, None)]
    tables = build_features(records, period=period)
    assert tables.observations.ler_id.tolist() == [str(records[0].ler_id)]
    assert set(tables.exclusions.reason) == {"missing_timestamp", "outside_period"}


def test_reproducible_under_input_permutation():
    records = [record(), record(102, 2, "2026-10-25T15:00:00Z")]
    first, second = build_features(records), build_features(list(reversed(records)))
    for name in ("observations", "outcomes", "errors", "practice", "exclusions"):
        pd.testing.assert_frame_equal(getattr(first, name), getattr(second, name))


def test_empty_dataset_has_stable_columns():
    tables = build_features([])
    assert tables.observations.empty and "score_ratio" in tables.observations.columns
    assert tables.outcomes.empty and "normalized_weight" in tables.outcomes.columns
    assert tables.errors.empty and "code" in tables.errors.columns


def test_overflowing_score_never_becomes_infinite_feature():
    first = record().model_copy(update={"points_earned": Decimal("1e1000"), "points_possible": Decimal("2e1000")})
    tables = build_features([first])
    assert not tables.observations.iloc[0].score_eligible
    assert pd.isna(tables.observations.iloc[0].score_ratio)


def test_incomplete_pair_preserves_available_source_points():
    tables = build_features([record(earned=6, possible=None)])
    row = tables.observations.iloc[0]
    assert row.source_points_earned == "6"
    assert row.source_points_possible is None
    assert pd.isna(row.points_earned) and pd.isna(row.score_ratio)


def test_course_and_student_are_distinct_aggregation_boundaries():
    first = record()
    other_student = record(102).model_copy(update={"learner_id": UUID(uid(301))})
    other_course = record(103).model_copy(update={"course_id": UUID(uid(302))})
    tables = build_features([other_course, first, other_student])
    assert len(primary_ids(tables)) == 3
    assert len(tables.observations) == 3


def test_one_practice_attempt_cannot_be_counted_under_two_origins():
    first = record().model_copy(update={
        "assessment_origin": "generated_practice", "practice_attempt_id": UUID(uid(800)),
    })
    conflicting = first.model_copy(update={
        "ler_id": UUID(uid(102)), "assessment_origin": "instructor_practice",
    })
    tables = build_features([first, conflicting])
    assert tables.practice.empty
    assert set(tables.exclusions.reason) == {"conflicting_question_attempt"}


def test_nested_reference_order_does_not_make_identical_lers_conflict():
    first = record()
    refs = [UUID(uid(900)), UUID(uid(901))]
    error = first.errors[0].model_copy(update={"evidence_ref_ids": refs})
    first = first.model_copy(update={"errors": [error], "evidence_ref_ids": refs})
    same = first.model_copy(update={"errors": [error.model_copy(update={"evidence_ref_ids": refs[::-1]})]})
    tables = build_features([first, same])
    assert len(tables.observations) == 1


def test_finite_extreme_weights_do_not_crash_normalization():
    first = record()
    mappings = [m.model_copy(update={"weight": Decimal("1e1000000")}) for m in first.outcome_mappings]
    tables = build_features([first.model_copy(update={"outcome_mappings": mappings})])
    assert tables.outcomes.normalized_weight.tolist() == [0.5, 0.5]
