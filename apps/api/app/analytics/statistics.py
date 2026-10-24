"""Evidence-linked descriptive statistics, independent of ARR persistence and UI.

Results are internal DTOs, not authorized HTTP responses. Aggregate suppression
removes small-cohort counts and links before these DTOs can reach a consumer.
"""

from decimal import Decimal
from math import fsum
from typing import Literal
from uuid import UUID

import pandas as pd
from pydantic import Field

from .config import AnalyticsConfig
from .contracts import AnalysisPeriod, AnalyticalInput, Contract, Count, Nonnegative, Ratio
from .features import FeatureTables, build_features


class ErrorStatistics(Contract):
    code: str
    occurrence_count: Count
    distinct_question_count: Count
    distinct_attempt_count: Count
    unique_student_count: Count
    recurring: bool
    evidence_ler_ids: list[UUID]
    evidence_ref_ids: list[UUID]


class PracticeStatistics(Contract):
    assistance: Literal["independent", "assisted", "unknown"]
    attempt_count: Count
    hints_known_count: Count
    hints_total: Count | None
    independently_correct_count: Count | None
    independent_correctness_known_count: Count
    independent_correctness_ratio: Ratio | None
    scored_attempt_count: Count
    weighted_earned: Nonnegative
    weighted_possible: Nonnegative
    observed_score_ratio: Ratio | None
    evidence_ler_ids: list[UUID]


class StudentOutcomeStatistics(Contract):
    course_id: UUID
    learner_id: UUID
    outcome_id: UUID
    observed_score_ratio: Ratio | None
    weighted_earned: Nonnegative
    weighted_possible: Nonnegative
    scored_observation_count: Count
    distinct_question_count: Count
    distinct_assessment_count: Count
    insufficient_evidence: bool
    errors: list[ErrorStatistics]
    error_assessed_observation_count: Count
    unattributed_error_observation_count: Count
    practice: list[PracticeStatistics]
    score_ler_ids: list[UUID]
    error_assessed_ler_ids: list[UUID]
    practice_ler_ids: list[UUID]
    mastery_estimate: None = None


class ErrorPrevalence(Contract):
    code: str
    numerator: Count | None
    denominator: Count | None
    prevalence: Ratio | None
    insufficient_evidence: bool
    suppressed: bool
    numerator_definition: str = "unique eligible students with this error category"
    denominator_definition: str = "unique independently assessed students with completed, usable error classification"
    evidence_ler_ids: list[UUID] = Field(default_factory=list)


class AggregateStatistics(Contract):
    scope: Literal["class_outcome", "assessment_question"]
    course_id: UUID
    outcome_id: UUID | None = None
    assessment_id: UUID | None = None
    question_id: UUID | None = None
    assessed_student_count: Count | None
    students_with_valid_scores: Count | None
    students_meeting_evidence_minimum: Count | None
    mean_student_ratio: Ratio | None
    pooled_score_ratio: Ratio | None
    pooled_weighted_earned: Nonnegative | None
    pooled_weighted_possible: Nonnegative | None
    observed_performance_threshold: Ratio
    at_or_above_threshold_count: Count | None
    below_threshold_count: Count | None
    evidence_coverage_ratio: Ratio | None
    coverage_basis: str = "students represented in eligible mapped assessment evidence; not enrollment"
    error_assessed_student_count: Count | None
    error_coverage_ratio: Ratio | None
    error_prevalence: list[ErrorPrevalence]
    errors: list[ErrorStatistics]
    insufficient_evidence: bool
    suppressed: bool
    evidence_ler_ids: list[UUID]
    assessment_breakdowns: list["AggregateStatistics"] = Field(default_factory=list)
    mastery_estimate: None = None


class StatisticsResult(Contract):
    config: AnalyticsConfig
    period: AnalysisPeriod | None
    student_outcomes: list[StudentOutcomeStatistics]
    class_outcomes: list[AggregateStatistics]
    assessment_questions: list[AggregateStatistics]


def _ids(frame, column="ler_id"):
    return sorted(set(frame[column].dropna()))


def _total(series):
    # Decimal avoids overflow when finite per-observation floats are pooled.
    return sum((Decimal(str(value)) for value in series), Decimal(0))


def _ratio(earned, possible):
    return float(earned / possible) if possible > 0 else None


def _error_summaries(events, config):
    summaries = []
    for code, group in events.groupby("code", sort=True):
        attempts = {
            (row.assessment_id, row.attempt_id, row.practice_attempt_id)
            for row in group.itertuples()
        }
        summaries.append(ErrorStatistics(
            code=code, occurrence_count=len(group),
            distinct_question_count=group.question_id.nunique(),
            distinct_attempt_count=len(attempts), unique_student_count=group.learner_id.nunique(),
            recurring=len(group) >= config.recurring_error_min_observations,
            evidence_ler_ids=_ids(group),
            evidence_ref_ids=sorted({ref for refs in group.evidence_ref_ids for ref in refs}),
        ))
    return summaries


def _outcome_errors(group, errors, outcome_id):
    candidates = group.loc[group.primary_error & group.error_policy_complete]
    events = errors.loc[errors.ler_id.isin(candidates.ler_id)]
    # A tag with no explicit outcome attribution cannot establish absence for an outcome.
    unattributed = set(events.loc[events.outcome_ids.map(lambda ids: not ids), "ler_id"])
    assessed = candidates.loc[~candidates.ler_id.isin(unattributed)]
    events = events.loc[
        events.ler_id.isin(assessed.ler_id) &
        events.outcome_ids.map(lambda ids: outcome_id in ids)
    ]
    return assessed, events, len(unattributed)


def _practice_summaries(group, config):
    results = []
    practice = group.loc[group.assessment_origin != "graded_canvas"]
    for assistance in ("independent", "assisted", "unknown"):
        attempts = practice.loc[practice.assistance == assistance]
        hints = attempts.hints_used.dropna()
        scored = attempts.loc[attempts.score_eligible & (attempts.weighted_possible > 0)]
        earned, possible = _total(scored.weighted_earned), _total(scored.weighted_possible)
        known = attempts.independent_correctness.dropna() if assistance == "independent" else pd.Series(dtype=bool)
        correct = int(known.astype(bool).sum()) if len(known) else None
        results.append(PracticeStatistics(
            assistance=assistance, attempt_count=len(attempts), hints_known_count=len(hints),
            hints_total=int(hints.sum()) if len(hints) else None,
            independently_correct_count=correct, independent_correctness_known_count=len(known),
            independent_correctness_ratio=correct / len(known) if len(known) >= config.practice_min_attempts else None,
            scored_attempt_count=len(scored), weighted_earned=earned, weighted_possible=possible,
            observed_score_ratio=_ratio(earned, possible) if len(scored) >= config.practice_min_attempts else None,
            evidence_ler_ids=_ids(attempts),
        ))
    return results


def _student(group, errors, config, course_id, learner_id, outcome_id):
    scores = group.loc[group.primary_score & (group.weighted_possible > 0)]
    earned, possible = _total(scores.weighted_earned), _total(scores.weighted_possible)
    questions = scores.question_id.nunique()
    sufficient = questions >= config.student_min_questions and possible > 0
    assessed_errors, events, unattributed_count = _outcome_errors(group, errors, outcome_id)
    practice = group.loc[group.assessment_origin != "graded_canvas"]
    return StudentOutcomeStatistics(
        course_id=course_id, learner_id=learner_id, outcome_id=outcome_id,
        observed_score_ratio=_ratio(earned, possible) if sufficient else None,
        weighted_earned=earned, weighted_possible=possible,
        scored_observation_count=len(scores), distinct_question_count=questions,
        distinct_assessment_count=scores.assessment_id.nunique(), insufficient_evidence=not sufficient,
        errors=_error_summaries(events, config), error_assessed_observation_count=len(assessed_errors),
        unattributed_error_observation_count=unattributed_count, practice=_practice_summaries(group, config),
        score_ler_ids=_ids(scores), error_assessed_ler_ids=_ids(assessed_errors),
        practice_ler_ids=_ids(practice),
    )


def _aggregate(group, errors, config, course_id, scope, outcome_id=None, assessment_id=None, question_id=None):
    graded = group.loc[group.assessment_origin == "graded_canvas"]
    scores = graded.loc[graded.primary_score & (graded.weighted_possible > 0)]
    assessed_count = graded.learner_id.nunique()
    valid_score_count = scores.learner_id.nunique()
    minimum = config.student_min_questions if scope == "class_outcome" else 1
    student_scores = []
    for learner_id, student in scores.groupby("learner_id", sort=True):
        earned, possible = _total(student.weighted_earned), _total(student.weighted_possible)
        if student.question_id.nunique() >= minimum and possible > 0:
            student_scores.append((learner_id, earned, possible, _ratio(earned, possible)))
    ratios = [row[3] for row in student_scores]
    valid_count = len(ratios)
    sufficient = valid_count >= config.class_min_students
    suppressed = config.suppress_small_cohorts and (
        assessed_count < config.class_min_students or 0 < valid_count < config.class_min_students
        or 0 < valid_score_count < config.class_min_students
    )
    earned = sum((row[1] for row in student_scores), Decimal(0))
    possible = sum((row[2] for row in student_scores), Decimal(0))
    if outcome_id is not None:
        error_assessed, events, _ = _outcome_errors(graded, errors, outcome_id)
    else:
        error_assessed = graded.loc[graded.primary_error & graded.error_policy_complete]
        events = errors.loc[errors.ler_id.isin(error_assessed.ler_id)]
    error_denominator = error_assessed.learner_id.nunique()
    error_sufficient = error_denominator >= config.class_min_students
    hide_errors = suppressed or (config.suppress_small_cohorts and not error_sufficient)
    prevalence = []
    # Never publish a category discovered only outside this denominator's evidence.
    if not hide_errors:
        for code, category in events.groupby("code", sort=True):
            numerator = category.learner_id.nunique()
            prevalence.append(ErrorPrevalence(
                code=code, numerator=None if hide_errors else numerator,
                denominator=None if hide_errors else error_denominator,
                prevalence=numerator / error_denominator if error_sufficient and not hide_errors else None,
                insufficient_evidence=not error_sufficient, suppressed=hide_errors,
                evidence_ler_ids=[] if hide_errors else _ids(category),
            ))
    above = sum(value >= config.observed_performance_threshold for value in ratios)
    result = AggregateStatistics(
        scope=scope, course_id=course_id, outcome_id=outcome_id,
        assessment_id=assessment_id, question_id=question_id,
        assessed_student_count=None if suppressed else assessed_count,
        students_with_valid_scores=None if suppressed else valid_score_count,
        students_meeting_evidence_minimum=None if suppressed else valid_count,
        mean_student_ratio=fsum(ratios) / valid_count if sufficient and not suppressed else None,
        pooled_score_ratio=_ratio(earned, possible) if sufficient and not suppressed else None,
        pooled_weighted_earned=None if suppressed else earned,
        pooled_weighted_possible=None if suppressed else possible,
        observed_performance_threshold=config.observed_performance_threshold,
        at_or_above_threshold_count=above if sufficient and not suppressed else None,
        below_threshold_count=valid_count - above if sufficient and not suppressed else None,
        evidence_coverage_ratio=valid_count / assessed_count if assessed_count and not suppressed else None,
        coverage_basis=("students represented in eligible mapped assessment evidence; not enrollment"
                        if scope == "class_outcome" else
                        "students represented in eligible assessment-question evidence; not enrollment"),
        error_assessed_student_count=None if hide_errors else error_denominator,
        error_coverage_ratio=error_denominator / assessed_count if assessed_count and not hide_errors else None,
        error_prevalence=prevalence, errors=[] if hide_errors else _error_summaries(events, config),
        insufficient_evidence=not sufficient, suppressed=suppressed,
        # Includes the observed cohort behind coverage/counts, not just scored students.
        evidence_ler_ids=[] if suppressed else _ids(graded),
    )
    if scope == "class_outcome" and assessment_id is None and not suppressed:
        result.assessment_breakdowns = [
            _aggregate(part, errors, config, course_id, scope, outcome_id, assessment_id=aid)
            for aid, part in graded.groupby("assessment_id", sort=True)
        ]
    return result


def analyze_statistics(
    records: list[AnalyticalInput], config: AnalyticsConfig | None = None,
    period: AnalysisPeriod | None = None,
) -> StatisticsResult:
    """Calculate all Phase 4 results from the same selected feature snapshot.

    Source cohort is observed input, not enrollment. Results include configuration
    and period; exclusions can be inspected via build_features on the same input.
    """
    config = config or AnalyticsConfig()
    features: FeatureTables = build_features(records, config, period)
    observations = features.observations
    result = StatisticsResult(config=config, period=period, student_outcomes=[], class_outcomes=[], assessment_questions=[])
    if observations.empty:
        return result
    mapped = features.outcomes.merge(
        observations.drop(columns=["primary_score", "evidence_ref_ids"]),
        on="ler_id", validate="many_to_one",
    )
    for (course_id, learner_id, outcome_id), group in mapped.groupby(["course_id", "learner_id", "outcome_id"], sort=True):
        result.student_outcomes.append(_student(group, features.errors, config, course_id, learner_id, outcome_id))
    for (course_id, outcome_id), group in mapped.groupby(["course_id", "outcome_id"], sort=True):
        if not group.loc[group.assessment_origin == "graded_canvas"].empty:
            result.class_outcomes.append(_aggregate(group, features.errors, config, course_id, "class_outcome", outcome_id))
    # Question statistics do not require outcome mappings. Each student contributes
    # one selected attempt; minimum question count is one for a question's statistic.
    graded = observations.loc[observations.assessment_origin == "graded_canvas"].copy()
    graded["weighted_earned"] = graded.points_earned
    graded["weighted_possible"] = graded.points_possible
    for (course_id, assessment_id, question_id), group in graded.groupby(["course_id", "assessment_id", "question_id"], sort=True):
        result.assessment_questions.append(_aggregate(
            group, features.errors, config, course_id, "assessment_question",
            assessment_id=assessment_id, question_id=question_id,
        ))
    return result
