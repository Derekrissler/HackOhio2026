"""Deterministic feature engineering. No aggregation, network or database access."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import json

import numpy as np
import pandas as pd

from .config import AnalyticsConfig
from .contracts import AnalysisPeriod, AnalyticalInput


OBSERVATION_COLUMNS = [
    "ler_id", "course_id", "learner_id", "assessment_id", "question_id", "attempt_id",
    "practice_attempt_id", "attempt_number", "observed_at", "assessment_origin",
    "assistance", "hints_used", "independent_correctness", "points_earned",
    "points_possible", "source_points_earned", "source_points_possible",
    "score_ratio", "score_eligible", "error_analysis_complete",
    "primary_score", "primary_error", "evidence_ref_ids",
]
OUTCOME_COLUMNS = [
    "ler_id", "outcome_id", "raw_weight", "normalized_weight", "weighted_earned",
    "weighted_possible", "primary_score", "evidence_ref_ids",
]
ERROR_COLUMNS = [
    "ler_id", "course_id", "learner_id", "assessment_id", "question_id", "attempt_id",
    "practice_attempt_id", "assessment_origin", "assistance", "observed_at", "code",
    "outcome_ids", "evidence_ref_ids", "primary_error",
]
PRACTICE_COLUMNS = [
    "ler_id", "course_id", "learner_id", "practice_attempt_id", "observed_at",
    "assessment_origin", "assistance", "hints_used", "independent_correctness", "outcome_ids",
    "evidence_ref_ids",
]
EXCLUSION_COLUMNS = ["ler_id", "stage", "reason"]


@dataclass
class FeatureTables:
    observations: pd.DataFrame
    outcomes: pd.DataFrame
    errors: pd.DataFrame
    practice: pd.DataFrame
    exclusions: pd.DataFrame


def _canonical(record, exclude_identity=False):
    data = record.model_dump(mode="json")
    if exclude_identity:
        data.pop("ler_id")
        data.pop("revision")
    # Order of mappings, tags and source references has no semantic significance.
    for key in ("outcome_mappings", "errors", "evidence_ref_ids"):
        data[key] = sorted(data[key], key=lambda item: json.dumps(item, sort_keys=True))
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def build_features(
    records: list[AnalyticalInput],
    config: AnalyticsConfig | None = None,
    period: AnalysisPeriod | None = None,
) -> FeatureTables:
    """Create history and explicit primary selections from validated input.

    Scoring uses independent graded evidence only. Error history can include
    unscored and assisted observations; primary errors use independent graded
    evidence with completed classification. Practice always remains separate.
    """
    config = config or AnalyticsConfig()
    exclusions = []

    def exclude(record, stage, reason):
        exclusions.append({"ler_id": str(record.ler_id), "stage": stage, "reason": reason})

    # Detect conflicts before filtering: input order must never choose a winner.
    by_id = defaultdict(list)
    for record in records:
        by_id[str(record.ler_id)].append(record)
    unique = []
    for _, group in sorted(by_id.items()):
        if len({_canonical(r) for r in group}) > 1:
            exclude(group[0], "deduplication", "conflicting_ler_id")
        else:
            unique.append(group[0])
            if len(group) > 1:
                exclude(group[0], "deduplication", "duplicate_ler_collapsed")

    eligible = []
    for record in unique:
        if not record.is_current:
            exclude(record, "eligibility", "superseded_ler")
        elif record.analysis_status != "analyzed":
            exclude(record, "eligibility", "insufficient_analysis")
        elif period is not None and record.observed_at is None:
            exclude(record, "period", "missing_timestamp")
        elif period is not None and not period.start <= record.observed_at < period.end:
            exclude(record, "period", "outside_period")
        else:
            eligible.append(record)

    # One observation per logical question-attempt, even if duplicated under new IDs.
    semantic = defaultdict(list)
    for record in eligible:
        key = (str(record.course_id), str(record.learner_id), record.assessment_origin,
               str(record.practice_attempt_id) if record.practice_attempt_id else
               (str(record.assessment_id), str(record.question_id), str(record.attempt_id)))
        semantic[key].append(record)
    retained = []
    for group in semantic.values():
        group.sort(key=lambda r: str(r.ler_id))
        if len({_canonical(r, exclude_identity=True) for r in group}) > 1:
            for record in group:
                exclude(record, "deduplication", "conflicting_question_attempt")
        else:
            retained.append(group[0])
            for record in group[1:]:
                exclude(record, "deduplication", "duplicate_question_attempt")
    retained.sort(key=lambda r: str(r.ler_id))

    def valid_score(record):
        if record.points_earned is None or record.points_possible is None:
            return False
        # Decimal inputs can be finite but exceed floating point feature range.
        values = np.array([float(record.points_earned), float(record.points_possible)])
        return bool(np.isfinite(values).all() and values[1] > 0)

    def select_primary(candidates, stage):
        groups = defaultdict(list)
        for record in candidates:
            groups[(record.course_id, record.learner_id, record.assessment_id, record.question_id)].append(record)
        selected = []
        for group in groups.values():
            if len(group) == 1:
                selected.append(group[0])
                continue
            if all(r.observed_at is not None for r in group):
                latest_time = max(r.observed_at for r in group)
                latest = [r for r in group if r.observed_at == latest_time]
                if len(latest) > 1 and all(r.attempt_number is not None for r in latest):
                    number = max(r.attempt_number for r in latest)
                    latest = [r for r in latest if r.attempt_number == number]
            elif all(r.attempt_number is not None for r in group):
                number = max(r.attempt_number for r in group)
                latest = [r for r in group if r.attempt_number == number]
            else:
                latest = []
            if len(latest) != 1:
                for record in group:
                    exclude(record, stage, "ambiguous_attempt_order")
                continue
            selected.append(latest[0])
            for record in group:
                if record is not latest[0]:
                    exclude(record, stage, "historical_attempt")

        # Whole-assessment observations overlap exam parts across attempts too.
        parts = {(r.course_id, r.learner_id, r.assessment_id) for r in selected
                 if r.question_type == "rubric_question_part"}
        result = set()
        for record in selected:
            if (record.question_type == "assignment_level" and
                    (record.course_id, record.learner_id, record.assessment_id) in parts):
                exclude(record, stage, "whole_assessment_overlaps_parts")
            else:
                result.add(record.ler_id)
        return result

    independent = [r for r in retained if r.assessment_origin == "graded_canvas" and r.assistance == "independent"]
    primary_scores = select_primary([r for r in independent if valid_score(r)], "primary_score")
    primary_errors = select_primary([r for r in independent if r.errors_analyzed is True], "primary_error")
    observations, outcomes, errors, practice = [], [], [], []
    for record in retained:
        rid = str(record.ler_id)
        scored = valid_score(record)
        if not scored:
            exclude(record, "score", "missing_invalid_or_unrepresentable_score")
        if record.assistance != "independent" and record.assessment_origin == "graded_canvas":
            exclude(record, "primary_score", "assisted_or_unknown_assessment")
        refs = sorted(map(str, set(record.evidence_ref_ids)))
        common = {
            "ler_id": rid, "course_id": str(record.course_id), "learner_id": str(record.learner_id),
            "assessment_id": str(record.assessment_id) if record.assessment_id else None,
            "question_id": str(record.question_id) if record.question_id else None,
            "attempt_id": str(record.attempt_id) if record.attempt_id else None,
            "practice_attempt_id": str(record.practice_attempt_id) if record.practice_attempt_id else None,
            "observed_at": record.observed_at, "assessment_origin": record.assessment_origin,
            "assistance": record.assistance,
        }
        observations.append({
            **common, "attempt_number": record.attempt_number, "hints_used": record.hints_used,
            "independent_correctness": record.independent_correctness,
            "points_earned": float(record.points_earned) if scored else None,
            "points_possible": float(record.points_possible) if scored else None,
            "source_points_earned": str(record.points_earned) if record.points_earned is not None else None,
            "source_points_possible": str(record.points_possible) if record.points_possible is not None else None,
            "score_ratio": float(record.points_earned / record.points_possible) if scored else None,
            "score_eligible": scored, "error_analysis_complete": record.errors_analyzed,
            "primary_score": record.ler_id in primary_scores,
            "primary_error": record.ler_id in primary_errors, "evidence_ref_ids": refs,
        })
        positive = [m for m in record.outcome_mappings if m.weight > 0]
        total = sum((m.weight for m in positive), Decimal(0))
        if not positive:
            exclude(record, "outcomes", "no_positive_outcome_weights")
        for mapping in sorted(positive, key=lambda m: str(m.outcome_id)):
            weight = float(mapping.weight / total)
            outcomes.append({
                "ler_id": rid, "outcome_id": str(mapping.outcome_id), "raw_weight": str(mapping.weight),
                "normalized_weight": weight,
                "weighted_earned": weight * float(record.points_earned) if scored else None,
                "weighted_possible": weight * float(record.points_possible) if scored else None,
                "primary_score": record.ler_id in primary_scores, "evidence_ref_ids": refs,
            })
        tags = defaultdict(list)
        for error in record.errors:
            if error.instructor_status == "rejected":
                continue
            if error.instructor_status == "unreviewed" and not config.include_unreviewed_errors:
                continue
            tags[error.code].append(error)
        if record.errors_analyzed is not True:
            exclude(record, "errors", "error_classification_incomplete")
        else:
            for code, group in sorted(tags.items()):
                errors.append({
                    **common, "code": code,
                    "outcome_ids": sorted({str(o) for e in group for o in e.outcome_ids}),
                    "evidence_ref_ids": sorted({str(eid) for e in group for eid in e.evidence_ref_ids}),
                    "primary_error": record.ler_id in primary_errors,
                })
        if record.assessment_origin != "graded_canvas":
            practice.append({
                **common, "hints_used": record.hints_used,
                "independent_correctness": record.independent_correctness,
                "outcome_ids": sorted(str(m.outcome_id) for m in positive), "evidence_ref_ids": refs,
            })

    def frame(rows, columns):
        # Explicit schemas remain available for empty datasets. Null scores stay null.
        return pd.DataFrame(rows, columns=columns)

    exclusions.sort(key=lambda row: (row["ler_id"], row["stage"], row["reason"]))
    return FeatureTables(
        observations=frame(observations, OBSERVATION_COLUMNS),
        outcomes=frame(outcomes, OUTCOME_COLUMNS), errors=frame(errors, ERROR_COLUMNS),
        practice=frame(practice, PRACTICE_COLUMNS), exclusions=frame(exclusions, EXCLUSION_COLUMNS),
    )
