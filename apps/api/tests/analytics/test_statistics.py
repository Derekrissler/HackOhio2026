from decimal import Decimal
from uuid import UUID

import pytest

from app.analytics.config import AnalyticsConfig
from app.analytics.contracts import AnalysisPeriod, AnalyticalInput
from app.analytics.statistics import StatisticsResult, analyze_statistics
from .test_features import record, uid


CONFIG = AnalyticsConfig(class_min_students=2)


def sample(number, student=1, question=1, earned=6, possible=10, error=False, **updates):
    original = record(number, earned=earned, possible=possible)
    mapping = original.outcome_mappings[0].model_copy(update={"weight": Decimal(1)})
    tag = original.errors[0].model_copy(update={"outcome_ids": [mapping.outcome_id]})
    data = original.model_dump()
    data.update(learner_id=UUID(uid(300 + student)), question_id=UUID(uid(400 + question)),
                outcome_mappings=[mapping], errors=[tag] if error else [])
    data.update(updates)
    return AnalyticalInput.model_validate(data)


def two_questions(student=1, start=101, earned=6, possible=10, error=False, **updates):
    return [sample(start + i, student, i + 1, earned, possible, error, **updates) for i in range(2)]


def test_hand_calculated_student_ratio_and_evidence_counts():
    records = [sample(101, question=1, earned=6, possible=10),
               sample(102, question=2, earned=18, possible=20)]
    student = analyze_statistics(records).student_outcomes[0]
    assert student.observed_score_ratio == pytest.approx(24 / 30)
    assert student.weighted_earned == 24 and student.weighted_possible == 30
    assert student.distinct_question_count == student.scored_observation_count == 2
    assert student.distinct_assessment_count == 1
    assert student.score_ler_ids == [r.ler_id for r in records]
    assert student.mastery_estimate is None


def test_score_threshold_requires_distinct_questions_not_repeated_attempts():
    first = sample(101)
    later = sample(102, attempt_id=UUID(uid(999)), attempt_number=2)
    student = analyze_statistics([first, later]).student_outcomes[0]
    assert student.distinct_question_count == 1
    assert student.observed_score_ratio is None and student.insufficient_evidence
    assert student.weighted_possible == 10


def test_weights_are_used_with_unequal_question_points():
    first = record(101, earned=6, possible=10)
    second = record(102, earned=18, possible=20)
    mappings = [m.model_copy(update={"weight": Decimal(w)}) for m, w in zip(second.outcome_mappings, (1, 3))]
    second = second.model_copy(update={"question_id": UUID(uid(990)), "outcome_mappings": mappings})
    students = analyze_statistics([first, second]).student_outcomes
    assert students[0].weighted_earned == 9  # .75*6 + .25*18
    assert students[0].weighted_possible == Decimal("12.5")
    assert students[0].observed_score_ratio == pytest.approx(0.72)
    assert students[1].observed_score_ratio == pytest.approx(15 / 17.5)


def test_class_mean_and_pooled_ratio_are_different_metrics():
    records = two_questions(1, 101, earned=2, possible=10) + two_questions(2, 201, earned=90, possible=100)
    aggregate = analyze_statistics(records, CONFIG).class_outcomes[0]
    assert aggregate.mean_student_ratio == pytest.approx(0.55)  # mean(.2, .9)
    assert aggregate.pooled_score_ratio == pytest.approx(184 / 220)
    assert aggregate.assessed_student_count == aggregate.students_with_valid_scores == 2
    assert aggregate.students_meeting_evidence_minimum == 2
    assert aggregate.at_or_above_threshold_count == aggregate.below_threshold_count == 1
    assert aggregate.evidence_coverage_ratio == 1


def test_extra_attempts_do_not_give_student_more_class_weight():
    records = two_questions(1, 101, earned=2) + two_questions(2, 201, earned=8)
    newer = [sample(301 + i, 1, i + 1, 4, 10, attempt_id=UUID(uid(950)), attempt_number=2) for i in range(2)]
    aggregate = analyze_statistics(records + newer, CONFIG).class_outcomes[0]
    assert aggregate.mean_student_ratio == pytest.approx(0.6)
    assert aggregate.assessed_student_count == 2


def test_error_recurrence_and_unique_student_prevalence():
    records = two_questions(1, 101, error=True) + two_questions(2, 201, error=False)
    results = analyze_statistics(records, CONFIG)
    error = results.student_outcomes[0].errors[0]
    assert error.occurrence_count == error.distinct_question_count == 2
    assert error.distinct_attempt_count == error.unique_student_count == 1
    assert error.recurring
    prevalence = results.class_outcomes[0].error_prevalence[0]
    assert prevalence.numerator == 1 and prevalence.denominator == 2
    assert prevalence.prevalence == 0.5
    assert prevalence.evidence_ler_ids == [r.ler_id for r in records[:2]]


def test_recurring_threshold_is_configurable():
    stats = analyze_statistics(two_questions(error=True), AnalyticsConfig(recurring_error_min_observations=3))
    assert not stats.student_outcomes[0].errors[0].recurring


def test_missing_scores_can_contribute_to_error_prevalence():
    records = two_questions(1, 101, earned=None, error=True) + two_questions(2, 201, earned=None)
    aggregate = analyze_statistics(records, CONFIG).class_outcomes[0]
    assert aggregate.insufficient_evidence and aggregate.mean_student_ratio is None
    assert aggregate.students_with_valid_scores == 0
    assert aggregate.error_prevalence[0].prevalence == 0.5


def test_unknown_outcome_attribution_does_not_become_no_error():
    records = two_questions(1, 101, error=True) + two_questions(2, 201)
    for r in records[:2]:
        r.errors[0].outcome_ids = []
    result = analyze_statistics(records, AnalyticsConfig(class_min_students=2, suppress_small_cohorts=False))
    student = result.student_outcomes[0]
    assert student.unattributed_error_observation_count == 2
    assert student.error_assessed_observation_count == 0
    assert student.errors == []
    aggregate = result.class_outcomes[0]
    assert aggregate.error_assessed_student_count == 1
    assert aggregate.error_prevalence == []


def test_unknown_error_classification_does_not_join_denominator():
    records = two_questions(1, 101, error=True) + two_questions(2, 201, errors_analyzed=None)
    result = analyze_statistics(records, AnalyticsConfig(class_min_students=2, suppress_small_cohorts=False))
    item = result.class_outcomes[0].error_prevalence[0]
    assert item.numerator == item.denominator == 1
    assert item.prevalence is None and item.insufficient_evidence


def test_unreviewed_exclusion_does_not_turn_unreviewed_errors_into_absence():
    records = two_questions(1, 101, error=True) + two_questions(2, 201)
    for r in records[:2]:
        r.errors[0].instructor_status = "unreviewed"
    config = AnalyticsConfig(class_min_students=2, include_unreviewed_errors=False, suppress_small_cohorts=False)
    result = analyze_statistics(records, config)
    assert result.student_outcomes[0].error_assessed_observation_count == 0
    assert result.class_outcomes[0].error_assessed_student_count == 1


def test_duplicate_tags_and_records_do_not_inflate_errors():
    records = two_questions(error=True)
    records[0].errors *= 3
    student = analyze_statistics(records + [records[0]]).student_outcomes[0]
    assert student.errors[0].occurrence_count == 2


def test_small_cohort_suppression_removes_counts_and_evidence():
    result = analyze_statistics(two_questions(error=True))
    for aggregate in result.class_outcomes + result.assessment_questions:
        assert aggregate.suppressed
        assert aggregate.assessed_student_count is None
        assert aggregate.pooled_weighted_earned is None
        assert aggregate.error_assessed_student_count is None
        assert aggregate.errors == aggregate.error_prevalence == aggregate.evidence_ler_ids == []
        assert aggregate.assessment_breakdowns == []


def test_minimum_denominator_does_not_disappear_when_suppression_disabled():
    result = analyze_statistics(two_questions(error=True), AnalyticsConfig(suppress_small_cohorts=False))
    aggregate = result.class_outcomes[0]
    assert aggregate.assessed_student_count == 1 and not aggregate.suppressed
    assert aggregate.mean_student_ratio is None
    assert aggregate.error_prevalence[0].numerator == aggregate.error_prevalence[0].denominator == 1
    assert aggregate.error_prevalence[0].prevalence is None


def test_valid_but_insufficient_student_count_is_distinguished():
    records = two_questions(1, 101) + [sample(201, 2)]
    result = analyze_statistics(records, AnalyticsConfig(suppress_small_cohorts=False))
    aggregate = result.class_outcomes[0]
    assert aggregate.assessed_student_count == aggregate.students_with_valid_scores == 2
    assert aggregate.students_meeting_evidence_minimum == 1
    assert aggregate.evidence_coverage_ratio == 0.5
    assert set(aggregate.evidence_ler_ids) == {r.ler_id for r in records}


def test_question_statistics_do_not_require_outcomes_or_two_questions():
    records = [sample(101, 1, earned=2, outcome_mappings=[]), sample(201, 2, earned=8, outcome_mappings=[])]
    result = analyze_statistics(records, CONFIG)
    assert result.class_outcomes == result.student_outcomes == []
    assert len(result.assessment_questions) == 1
    question = result.assessment_questions[0]
    assert question.mean_student_ratio == question.pooled_score_ratio == 0.5


def test_assessment_breakdowns_recompute_student_measures_within_each_assessment():
    records = []
    for s in (1, 2):
        records += two_questions(s, 100 * s + 1, earned=2)
        records += two_questions(s, 100 * s + 11, earned=8, assessment_id=UUID(uid(800)),
                                 attempt_id=UUID(uid(801)))
    result = analyze_statistics(records, CONFIG).class_outcomes[0]
    assert result.mean_student_ratio == 0.5
    assert sorted(item.mean_student_ratio for item in result.assessment_breakdowns) == [0.2, 0.8]


def practice(number, assistance, hints=None, correct=None):
    return sample(number, assistance=assistance, hints_used=hints, independent_correctness=correct,
                  assessment_origin="generated_practice", practice_attempt_id=UUID(uid(number + 5000)),
                  assessment_id=None, attempt_id=None, response_id=None, question_id=None,
                  assessment_type=None, points_earned=None, points_possible=None)


def test_practice_is_separate_and_missing_hints_are_not_zero():
    records = two_questions(earned=8) + [practice(201, "independent", 0, True),
                                       practice(202, "independent", None, False),
                                       practice(203, "assisted", 3, True),
                                       practice(204, "unknown")]
    student = analyze_statistics(records).student_outcomes[0]
    assert student.observed_score_ratio == 0.8
    independent, assisted, unknown = student.practice
    assert independent.attempt_count == 2 and independent.independent_correctness_ratio == 0.5
    assert independent.hints_known_count == 1 and independent.hints_total == 0
    assert assisted.hints_total == 3 and assisted.independently_correct_count is None
    assert assisted.independent_correctness_ratio is None
    assert unknown.hints_total is None
    assert len(student.score_ler_ids) == 2 and len(student.practice_ler_ids) == 4


def test_empty_and_ineligible_input_do_not_fabricate_statistics():
    assert analyze_statistics([]).student_outcomes == []
    result = analyze_statistics([sample(101, analysis_status="insufficient")])
    assert result.student_outcomes == result.class_outcomes == result.assessment_questions == []


def test_period_filters_before_attempt_selection():
    period = AnalysisPeriod(start="2026-10-24T00:00:00Z", end="2026-10-25T00:00:00Z")
    older = two_questions(earned=4)
    newer = two_questions(start=201, earned=9, observed_at="2026-10-26T00:00:00Z", attempt_id=UUID(uid(950)))
    result = analyze_statistics(older + newer, period=period)
    assert result.student_outcomes[0].observed_score_ratio == 0.4
    assert result.period == period


def test_result_is_reproducible_and_machine_readable():
    records = two_questions(1, 101, error=True) + two_questions(2, 201, earned=8)
    first = analyze_statistics(records, CONFIG)
    second = analyze_statistics(records[::-1], CONFIG)
    assert first.model_dump_json() == second.model_dump_json()
    assert StatisticsResult.model_validate_json(first.model_dump_json()) == first


def test_default_five_student_cohort_is_publishable():
    records = [r for student in range(1, 6) for r in two_questions(student, student * 100 + 1)]
    aggregate = analyze_statistics(records).class_outcomes[0]
    assert not aggregate.suppressed and not aggregate.insufficient_evidence
    assert aggregate.mean_student_ratio == 0.6
    assert aggregate.students_meeting_evidence_minimum == 5


def test_courses_are_never_pooled():
    records = two_questions() + two_questions(start=201, earned=9, course_id=UUID(uid(9999)))
    result = analyze_statistics(records)
    assert len(result.class_outcomes) == len(result.student_outcomes) == 2
    assert [s.observed_score_ratio for s in result.student_outcomes] == [0.9, 0.6]


def test_zero_is_a_real_score_not_missing_data():
    student = analyze_statistics(two_questions(earned=0)).student_outcomes[0]
    assert student.observed_score_ratio == 0
    assert not student.insufficient_evidence
    assert student.weighted_possible == 20


def test_whole_assessment_does_not_inflate_student_or_class_statistics():
    records = two_questions(1, 101, earned=6) + two_questions(2, 201, earned=8)
    for student in (1, 2):
        records.append(sample(500 + student, student, 90, earned=100, possible=100,
                              question_type="assignment_level"))
    aggregate = analyze_statistics(records, CONFIG).class_outcomes[0]
    assert aggregate.mean_student_ratio == pytest.approx(0.7)
    assert aggregate.pooled_weighted_possible == 40


def test_small_error_denominator_is_hidden_even_when_score_cohort_is_large():
    records = two_questions(1, 101, error=True) + two_questions(2, 201, errors_analyzed=None)
    aggregate = analyze_statistics(records, CONFIG).class_outcomes[0]
    assert not aggregate.suppressed
    assert aggregate.mean_student_ratio == 0.6
    assert aggregate.error_assessed_student_count is None
    assert aggregate.errors == aggregate.error_prevalence == []


def test_practice_minimum_is_recorded_in_configuration():
    records = [practice(201, "independent", 0, True), practice(202, "independent", 0, True)]
    result = analyze_statistics(records, AnalyticsConfig(practice_min_attempts=3))
    assert result.student_outcomes[0].practice[0].independent_correctness_ratio is None
    assert result.config.practice_min_attempts == 3


def test_finite_large_points_can_be_pooled_without_float_overflow():
    records = two_questions(1, 101, earned="5e307", possible="1e308")
    records += two_questions(2, 201, earned="1e308", possible="1e308")
    result = analyze_statistics(records, CONFIG)
    assert result.class_outcomes[0].pooled_weighted_possible == Decimal("4e308")
    assert result.class_outcomes[0].pooled_score_ratio == 0.75


def test_unscored_student_is_counted_in_observed_coverage():
    records = two_questions(1, 101) + two_questions(2, 201) + two_questions(3, 301, possible=0)
    aggregate = analyze_statistics(records, CONFIG).class_outcomes[0]
    assert aggregate.assessed_student_count == 3
    assert aggregate.students_with_valid_scores == aggregate.students_meeting_evidence_minimum == 2
    assert aggregate.evidence_coverage_ratio == pytest.approx(2 / 3)


def test_missing_timestamps_do_not_become_a_trend_or_enter_a_bounded_period():
    records = two_questions(observed_at=None)
    assert analyze_statistics(records).student_outcomes[0].observed_score_ratio == 0.6
    period = AnalysisPeriod(start="2026-10-24T00:00:00Z", end="2026-10-25T00:00:00Z")
    assert analyze_statistics(records, period=period).student_outcomes == []
