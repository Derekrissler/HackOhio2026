"""Prepare approved, error-specific excerpts; never mine arbitrary LER payloads."""

import hashlib
import json
import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import Field

from .config import AnalyticsConfig
from .contracts import AnalysisPeriod, AnalyticalInput, Contract
from .features import build_features


class ApprovedErrorText(Contract):
    ler_id: UUID
    error_code: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1000)
    source_kind: Literal["instructor_feedback", "error_description"]
    evidence_ref_ids: list[UUID] = Field(min_length=1)
    # This is an explicit caller attestation, not automated PII detection.
    privacy_reviewed: Literal[True]


class PreparedText(Contract):
    observation_id: str = Field(pattern=r"^text:[0-9a-f]{64}$")
    ler_id: UUID
    course_id: UUID
    learner_id: UUID
    question_id: UUID | None
    attempt_id: UUID | None
    practice_attempt_id: UUID | None
    assessment_origin: Literal["graded_canvas", "instructor_practice", "generated_practice"]
    assistance: Literal["independent", "assisted", "unknown"]
    error_code: str
    text: str
    source_kind: Literal["instructor_feedback", "error_description"]
    outcome_ids: list[UUID]
    evidence_ref_ids: list[UUID]


class TextExclusion(Contract):
    ler_id: UUID
    error_code: str
    reason: str


class PreparedTexts(Contract):
    observations: list[PreparedText]
    exclusions: list[TextExclusion]
    normalization_version: Literal["nfc_whitespace_v1"] = "nfc_whitespace_v1"


def normalize_error_text(text: str) -> str:
    # NFC and whitespace only: retain case, negations, inequalities and units.
    return " ".join(unicodedata.normalize("NFC", text).split())


def prepare_error_texts(
    records: list[AnalyticalInput], excerpts: list[ApprovedErrorText],
    config: AnalyticsConfig | None = None, period: AnalysisPeriod | None = None,
) -> PreparedTexts:
    config = config or AnalyticsConfig()
    features = build_features(records, config, period)
    observations = {row.ler_id: row for row in features.observations.itertuples()}
    events = {(row.ler_id, row.code): row for row in features.errors.itertuples()}
    buckets, excluded = {}, []
    for excerpt in excerpts:
        key = (str(excerpt.ler_id), excerpt.error_code)
        row, event = observations.get(key[0]), events.get(key)
        reason = None
        if row is None or event is None:
            reason = "no_eligible_error_event"
        elif row.assessment_origin == "graded_canvas" and not row.primary_error:
            reason = "not_selected_independent_classification"
        elif not row.error_policy_complete:
            reason = "incomplete_error_classification"
        elif not set(map(str, excerpt.evidence_ref_ids)) <= set(event.evidence_ref_ids):
            reason = "excerpt_not_linked_to_error_evidence"
        text = normalize_error_text(excerpt.text)
        if not text:
            reason = "empty_text"
        if reason:
            excluded.append(TextExclusion(ler_id=excerpt.ler_id, error_code=excerpt.error_code, reason=reason))
            continue
        buckets.setdefault(key, []).append((text, excerpt))
    prepared = []
    for key, candidates in sorted(buckets.items()):
        # Multiple fragments must not manufacture density for one error observation.
        text, excerpt = min(candidates, key=lambda pair: (
            len(pair[0]), pair[0], pair[1].source_kind,
            tuple(sorted(map(str, pair[1].evidence_ref_ids))),
        ))
        row, event = observations[key[0]], events[key]
        digest = hashlib.sha256(json.dumps([*key, text], ensure_ascii=False).encode()).hexdigest()
        prepared.append(PreparedText(
            observation_id=f"text:{digest}", ler_id=row.ler_id, course_id=row.course_id,
            learner_id=row.learner_id, question_id=row.question_id, attempt_id=row.attempt_id,
            practice_attempt_id=row.practice_attempt_id, assessment_origin=row.assessment_origin,
            assistance=row.assistance, error_code=key[1], text=text, source_kind=excerpt.source_kind,
            outcome_ids=event.outcome_ids,
            evidence_ref_ids=sorted({ref for _, item in candidates for ref in item.evidence_ref_ids}, key=str),
        ))
    excluded.sort(key=lambda item: (str(item.ler_id), item.error_code, item.reason))
    return PreparedTexts(observations=prepared, exclusions=excluded)
