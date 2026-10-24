"""Analytics boundary models, mapped to the existing Supabase schema.

These are analytics DTOs, not replacements for the extraction team's LER payload.
"""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from .config import AnalyticsConfig

Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, strict=True)]
Ratio = Annotated[float, Field(ge=0, le=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OutcomeMapping(Contract):
    outcome_id: UUID
    weight: Nonnegative
    provenance: Literal["ai", "instructor", "question_mapping"]
    needs_review: bool


class ErrorObservation(Contract):
    code: str = Field(min_length=1)
    misconception: str | None = None
    instructor_status: Literal["unreviewed", "confirmed", "rejected"]
    evidence_ref_ids: list[UUID]
    # Empty means outcome association is unavailable, not every mapped outcome.
    outcome_ids: list[UUID] = Field(default_factory=list)


class AnalyticalInput(Contract):
    ler_id: UUID
    schema_version: Literal["1.0"]
    course_id: UUID
    learner_id: UUID
    assessment_id: UUID | None = None
    question_id: UUID | None = None
    attempt_id: UUID | None = None
    response_id: UUID | None = None
    practice_attempt_id: UUID | None = None
    revision: int = Field(ge=1, strict=True)
    is_current: bool
    assessment_type: Literal["homework", "quiz", "exam", "project", "practice"] | None = None
    assessment_origin: Literal["graded_canvas", "instructor_practice", "generated_practice"]
    question_type: str | None = None
    attempt_number: int | None = Field(default=None, ge=1, strict=True)
    observed_at: AwareDatetime | None = None
    points_earned: Nonnegative | None = None
    points_possible: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)] | None = None
    assistance: Literal["independent", "assisted", "unknown"] = "unknown"
    hints_used: Count | None = None
    independent_correctness: bool | None = None
    analysis_status: Literal["analyzed", "insufficient"]
    outcome_mappings: list[OutcomeMapping]
    errors: list[ErrorObservation]
    errors_analyzed: bool | None = None
    evidence_ref_ids: list[UUID]

    @model_validator(mode="after")
    def consistent(self):
        if self.assessment_origin == "graded_canvas":
            if any(value is None for value in (
                self.assessment_id, self.question_id, self.attempt_id, self.response_id,
            )):
                raise ValueError("graded evidence needs assessment, question, attempt and response IDs")
            if not self.assessment_type:
                raise ValueError("graded evidence needs assessment_type")
        elif self.practice_attempt_id is None:
            raise ValueError("practice evidence needs practice_attempt_id")
        if self.points_earned is not None and self.points_possible is not None:
            if self.points_earned > self.points_possible:
                raise ValueError("extra credit requires an explicit scoring policy")
        ids = [m.outcome_id for m in self.outcome_mappings]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate outcome mappings")
        if self.assistance == "independent" and (self.hints_used or 0) > 0:
            raise ValueError("independent evidence cannot have hints")
        if self.errors_analyzed is False and self.errors:
            raise ValueError("error tags contradict errors_analyzed=false")
        refs = set(self.evidence_ref_ids)
        if any(not set(error.evidence_ref_ids) <= refs for error in self.errors):
            raise ValueError("error evidence must be included in source evidence references")
        return self


class AnalysisPeriod(Contract):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end:
            raise ValueError("period must be a nonempty [start, end) window")
        return self


class RunMetadata(Contract):
    id: UUID
    course_id: UUID
    method: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    input_snapshot: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    params: AnalyticsConfig
    started_at: AwareDatetime
    computed_at: AwareDatetime | None = None
    model_information: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered(self):
        if self.computed_at is not None and self.computed_at < self.started_at:
            raise ValueError("computation cannot precede run start")
        return self


class InterpretationLimits(Contract):
    insufficient_evidence: bool
    incomplete_coverage: bool
    suppressed: bool = False
    validated_mastery_model: Literal[False] = False
    reasons: list[str] = Field(default_factory=list)


class EvidenceSets(Contract):
    score_ler_ids: list[UUID] = Field(default_factory=list)
    error_ler_ids: list[UUID] = Field(default_factory=list)
    practice_ler_ids: list[UUID] = Field(default_factory=list)
    cluster_ler_ids: list[UUID] = Field(default_factory=list)
    trend_ler_ids: list[UUID] = Field(default_factory=list)


class PerformanceMetrics(Contract):
    observed_score_ratio: Ratio | None
    weighted_earned: Nonnegative
    weighted_possible: Nonnegative
    scored_observation_count: Count
    distinct_question_count: Count
    distinct_assessment_count: Count
    # Detailed, versioned subcontracts will be extended alongside their calculations.
    error_counts: dict[str, Count] = Field(default_factory=dict)
    independent_practice_count: Count = 0
    assisted_practice_count: Count = 0
    unknown_assistance_practice_count: Count = 0
    mastery_estimate: None = None

    @model_validator(mode="after")
    def valid_denominator(self):
        if self.observed_score_ratio is not None and self.weighted_possible == 0:
            raise ValueError("a score ratio requires a positive denominator")
        if self.weighted_earned > self.weighted_possible:
            raise ValueError("earned exceeds possible")
        return self


class ClassMetrics(Contract):
    assessed_student_count: Count
    valid_student_count: Count
    mean_student_ratio: Ratio | None
    pooled_score_ratio: Ratio | None
    at_or_above_threshold_count: Count | None
    below_threshold_count: Count | None
    mastery_estimate: None = None

    @model_validator(mode="after")
    def consistent_counts(self):
        if self.valid_student_count > self.assessed_student_count:
            raise ValueError("valid students exceed assessed students")
        above, below = self.at_or_above_threshold_count, self.below_threshold_count
        if (above is None) != (below is None):
            raise ValueError("threshold counts must be present or absent together")
        if above is not None and above + below != self.valid_student_count:
            raise ValueError("threshold counts must sum to valid students")
        if self.valid_student_count == 0 and (
            self.mean_student_ratio is not None or self.pooled_score_ratio is not None
        ):
            raise ValueError("no performance estimate without valid students")
        return self


class ClusterMetrics(Contract):
    cluster_id: str = Field(min_length=1)  # local to run_id
    observation_count: Count
    unique_student_count: Count
    distinct_question_count: Count
    outcome_ids: list[UUID]
    # Labels select an existing category, never an invented diagnosis.
    representative_error_code: str | None = None
    representative_evidence_ref_ids: list[UUID]
    member_ler_ids: list[UUID]
    embedding_model: str
    embedding_revision: str
    algorithm: Literal["dbscan_cosine"]
    parameters: dict[str, JsonValue]
    mastery_estimate: None = None


class TrendMetrics(Contract):
    earlier_period: AnalysisPeriod
    later_period: AnalysisPeriod
    earlier_ratio: Ratio | None
    later_ratio: Ratio | None
    descriptive_change: Annotated[float, Field(ge=-1, le=1)] | None
    mastery_estimate: None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.earlier_period.end > self.later_period.start:
            raise ValueError("trend windows must not overlap")
        if self.descriptive_change is not None:
            if self.earlier_ratio is None or self.later_ratio is None:
                raise ValueError("change needs both ratios")
            if abs(self.descriptive_change - (self.later_ratio - self.earlier_ratio)) > 1e-12:
                raise ValueError("change differs from later minus earlier")
        return self


class ARRBase(Contract):
    id: UUID
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    course_id: UUID
    evidence_ler_ids: list[UUID]
    evidence_sets: EvidenceSets
    inclusion_rule: str = Field(min_length=1)
    numerator_definition: str = Field(min_length=1)
    denominator_definition: str = Field(min_length=1)
    period: AnalysisPeriod | None = None
    interpretation_limits: InterpretationLimits
    created_at: AwareDatetime

    @model_validator(mode="after")
    def evidence_consistency(self):
        ids = self.evidence_ler_ids
        sets = self.evidence_sets.model_dump().values()
        union = {item for group in sets for item in group}
        if len(ids) != len(set(ids)) or set(ids) != union:
            raise ValueError("evidence_ler_ids must be the distinct union of metric evidence sets")
        for group in self.evidence_sets.model_dump().values():
            if len(group) != len(set(group)):
                raise ValueError("duplicate metric evidence ID")
        if self.interpretation_limits.suppressed:
            raise ValueError("suppressed aggregates require a separate redacted delivery contract")
        return self


class StudentOutcomeARR(ARRBase):
    scope: Literal["student_outcome"]
    subject_learner_id: UUID
    outcome_id: UUID
    metrics: PerformanceMetrics

    @model_validator(mode="after")
    def score_count_linked(self):
        if self.metrics.scored_observation_count != len(self.evidence_sets.score_ler_ids):
            raise ValueError("scored observation count must match selected score LERs")
        return self


class ClassOutcomeARR(ARRBase):
    scope: Literal["class_outcome"]
    outcome_id: UUID
    metrics: ClassMetrics


class AssessmentQuestionARR(ARRBase):
    scope: Literal["assessment_question"]
    assessment_id: UUID
    question_id: UUID
    metrics: ClassMetrics


class MisconceptionClusterARR(ARRBase):
    scope: Literal["misconception_cluster"]
    metrics: ClusterMetrics

    @model_validator(mode="after")
    def members_linked(self):
        if set(self.metrics.member_ler_ids) != set(self.evidence_sets.cluster_ler_ids):
            raise ValueError("cluster members must match cluster evidence")
        return self


class LongitudinalTrendARR(ARRBase):
    scope: Literal["longitudinal_trend"]
    outcome_id: UUID
    # Database disallows a subject on this scope; student trends belong in student ARRs.
    metrics: TrendMetrics


ARR = Annotated[
    StudentOutcomeARR | ClassOutcomeARR | AssessmentQuestionARR
    | MisconceptionClusterARR | LongitudinalTrendARR,
    Field(discriminator="scope"),
]
ARR_ADAPTER = TypeAdapter(ARR)
