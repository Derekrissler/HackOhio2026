"""Version 1.1 ARR documents and explicit mapping to the existing SQL columns.

The original 1.0 models remain readable scaffolds. New documents retain the full
typed Phase 4/5 metrics, including redacted aggregates, without changing SQL.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid5

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from .clustering import ClusterAssignment, ClusteringResult, MisconceptionGroup
from .contracts import AnalysisPeriod, AnalyticalInput, Contract, EvidenceSets, InterpretationLimits, Nonnegative
from .provenance import METHOD
from .statistics import AggregateStatistics, StatisticsResult, StudentOutcomeStatistics


class MetricEvidence(EvidenceSets):
    cohort_ler_ids: list[UUID] = Field(default_factory=list)


class ClusterResultMetrics(Contract):
    group: MisconceptionGroup
    assignments: list[ClusterAssignment]
    assessment_origin: str
    assistance: str
    mastery_estimate: None = None


class ARRDocument(Contract):
    id: UUID
    schema_version: Literal["1.1"] = "1.1"
    run_id: UUID
    course_id: UUID
    scope: Literal["student_outcome", "class_outcome", "assessment_question", "misconception_cluster"]
    subject_learner_id: UUID | None = None
    outcome_id: UUID | None = None
    assessment_id: UUID | None = None
    question_id: UUID | None = None
    metrics: StudentOutcomeStatistics | AggregateStatistics | ClusterResultMetrics
    evidence_sets: MetricEvidence
    evidence_ler_ids: list[UUID]
    dependency_ler_ids: list[UUID]
    numerator: Nonnegative | None = None
    denominator: Nonnegative | None = None
    numerator_definition: str
    denominator_definition: str
    inclusion_rule: str
    period: AnalysisPeriod | None
    interpretation_limits: InterpretationLimits
    provenance: dict[str, JsonValue]
    created_at: AwareDatetime

    @model_validator(mode="after")
    def consistent(self):
        union = {item for values in self.evidence_sets.model_dump().values() for item in values}
        if len(self.evidence_ler_ids) != len(set(self.evidence_ler_ids)) or set(self.evidence_ler_ids) != union:
            raise ValueError("metric evidence must equal its distinct declared union")
        if not union <= set(self.dependency_ler_ids):
            raise ValueError("metric evidence must be included in declared dependencies")
        if len(self.dependency_ler_ids) != len(set(self.dependency_ler_ids)):
            raise ValueError("duplicate dependency")
        if self.scope == "student_outcome":
            if not isinstance(self.metrics, StudentOutcomeStatistics) or self.subject_learner_id is None:
                raise ValueError("student scope requires typed student metrics and subject")
            if (self.course_id, self.subject_learner_id, self.outcome_id) != (
                self.metrics.course_id, self.metrics.learner_id, self.metrics.outcome_id,
            ) or self.assessment_id is not None or self.question_id is not None:
                raise ValueError("student dimensions disagree with metrics")
            if set(self.evidence_sets.score_ler_ids) != set(self.metrics.score_ler_ids):
                raise ValueError("student score evidence mismatch")
            if self.metrics.scored_observation_count != len(self.evidence_sets.score_ler_ids):
                raise ValueError("student score count mismatch")
            expected_sets = MetricEvidence(score_ler_ids=self.metrics.score_ler_ids,
                                           error_ler_ids=self.metrics.error_assessed_ler_ids,
                                           practice_ler_ids=self.metrics.practice_ler_ids)
            if {key: set(value) for key, value in self.evidence_sets.model_dump().items()} != {
                key: set(value) for key, value in expected_sets.model_dump().items()
            }:
                raise ValueError("student metric evidence mismatch")
            if (self.numerator, self.denominator) != (self.metrics.weighted_earned, self.metrics.weighted_possible):
                raise ValueError("student weighted point columns mismatch")
            ratio = self.metrics.observed_score_ratio
            if ratio is not None and (self.metrics.weighted_possible <= 0 or
                    abs(ratio - float(self.metrics.weighted_earned / self.metrics.weighted_possible)) > 1e-12):
                raise ValueError("student ratio differs from weighted points")
            if self.metrics.insufficient_evidence and ratio is not None:
                raise ValueError("insufficient student evidence cannot have a ratio")
            if self.metrics.distinct_question_count > self.metrics.scored_observation_count:
                raise ValueError("student distinct counts exceed observations")
        else:
            if self.subject_learner_id is not None:
                raise ValueError("nonstudent scope cannot have a subject")
            if self.scope in ("class_outcome", "assessment_question"):
                if not isinstance(self.metrics, AggregateStatistics) or self.metrics.scope != self.scope:
                    raise ValueError("aggregate metrics mismatch")
                if (self.course_id, self.outcome_id, self.assessment_id, self.question_id) != (
                    self.metrics.course_id, self.metrics.outcome_id, self.metrics.assessment_id, self.metrics.question_id,
                ):
                    raise ValueError("aggregate dimensions mismatch")
                if self.scope == "class_outcome" and self.outcome_id is None:
                    raise ValueError("class outcome required")
                if self.scope == "class_outcome" and self.question_id is not None:
                    raise ValueError("class scope cannot have a question")
                if self.scope == "assessment_question" and (self.assessment_id is None or self.question_id is None):
                    raise ValueError("question dimensions required")
                if self.metrics.suppressed != self.interpretation_limits.suppressed:
                    raise ValueError("suppression flags disagree")
                if set(self.evidence_sets.cohort_ler_ids) != set(self.metrics.evidence_ler_ids):
                    raise ValueError("aggregate cohort evidence mismatch")
                mean = self.metrics.mean_student_ratio
                if mean is None:
                    if self.numerator is not None or self.denominator is not None:
                        raise ValueError("unavailable class mean cannot have point columns")
                elif (self.denominator != self.metrics.students_meeting_evidence_minimum
                      or not self.denominator or self.numerator is None
                      or abs(float(self.numerator / self.denominator) - mean) > 1e-12):
                    raise ValueError("class mean numerator/denominator mismatch")
            elif not isinstance(self.metrics, ClusterResultMetrics):
                raise ValueError("cluster metrics required")
            elif any(value is not None for value in (self.outcome_id, self.assessment_id, self.question_id)):
                raise ValueError("cluster outcomes belong inside typed group metrics")
            else:
                group = self.metrics.group
                if set(self.evidence_sets.cluster_ler_ids) != set(group.evidence_ler_ids):
                    raise ValueError("cluster member evidence mismatch")
                if group.evidence_observation_count != len(set(group.evidence_ler_ids)):
                    raise ValueError("cluster evidence count mismatch")
                if group.text_observation_count != len(self.metrics.assignments):
                    raise ValueError("cluster assignment count mismatch")
                if any(item.cluster_id != group.cluster_id for item in self.metrics.assignments):
                    raise ValueError("cluster assignment belongs to another group")
        if self.interpretation_limits.suppressed:
            if not isinstance(self.metrics, AggregateStatistics):
                raise ValueError("only aggregate placeholders may be suppressed")
            sensitive = (
                self.metrics.assessed_student_count, self.metrics.students_with_valid_scores,
                self.metrics.students_meeting_evidence_minimum, self.metrics.mean_student_ratio,
                self.metrics.pooled_score_ratio, self.metrics.pooled_weighted_earned,
                self.metrics.pooled_weighted_possible, self.metrics.at_or_above_threshold_count,
                self.metrics.below_threshold_count, self.metrics.evidence_coverage_ratio,
                self.metrics.error_assessed_student_count, self.metrics.error_coverage_ratio,
                self.numerator, self.denominator,
            )
            if any(value is not None for value in sensitive) or any((
                self.evidence_ler_ids, self.dependency_ler_ids, self.metrics.evidence_ler_ids,
                self.metrics.errors, self.metrics.error_prevalence, self.metrics.assessment_breakdowns,
            )):
                raise ValueError("suppressed ARR contains sensitive measurements or evidence")
        return self

    def database_row(self, *, is_stale=True):
        # One versioned envelope in JSONB; indexed dimensions remain actual SQL columns.
        data = self.model_dump(mode="json")
        return {
            key: data[key] for key in (
                "id", "schema_version", "run_id", "course_id", "scope", "subject_learner_id",
                "outcome_id", "assessment_id", "question_id", "numerator", "denominator",
                "inclusion_rule", "interpretation_limits", "created_at",
            )
        } | {
            "metrics": {"document": data}, "error_code": None, "is_stale": is_stale,
            "period_start": data["period"]["start"] if data["period"] else None,
            "period_end": data["period"]["end"] if data["period"] else None,
        }


def document_from_row(row):
    document = ARRDocument.model_validate(row["metrics"]["document"])
    expected = document.database_row(is_stale=row["is_stale"])
    # Postgres numeric output may be numbers while our exact JSON uses decimal strings.
    for key, value in expected.items():
        if key in ("numerator", "denominator"):
            if (value is None) != (row.get(key) is None):
                raise ValueError("stored numeric columns disagree with ARR")
            if value is not None and abs(Decimal(str(row[key])) - Decimal(value)) > Decimal("1e-12"):
                raise ValueError("stored numeric columns disagree with ARR")
        elif key in ("created_at", "period_start", "period_end"):
            # Timestamp presentation (Z vs +00:00) is not analytical content.
            from pydantic import TypeAdapter
            if value is None:
                if row.get(key) is not None:
                    raise ValueError("stored period disagrees with ARR")
            elif TypeAdapter(AwareDatetime).validate_python(row[key]) != TypeAdapter(AwareDatetime).validate_python(value):
                raise ValueError("stored timestamps disagree with ARR")
        elif row.get(key) != value:
            raise ValueError("stored columns disagree with ARR document")
    return document


def generate_arrs(
    statistics: StatisticsResult, *, records: list[AnalyticalInput], run_id: UUID,
    input_snapshot: str, computed_at, clustering: ClusteringResult | None = None, approved_clusters=None,
) -> list[ARRDocument]:
    documents = []
    provenance = {"method": METHOD, "input_snapshot": input_snapshot,
                  "configuration": statistics.config.model_dump(mode="json"),
                  "model": clustering.model.model_dump(mode="json") if clustering and clustering.model else None}

    def append(scope, course_id, metrics, evidence, *, subject=None, outcome=None,
               assessment=None, question=None, token="", numerator=None, denominator=None,
               numerator_definition="not applicable", denominator_definition="not applicable",
               insufficient=False, suppressed=False, incomplete=True):
        used = sorted({item for ids in evidence.model_dump().values() for item in ids}, key=str)
        dependencies = [] if suppressed else sorted({r.ler_id for r in records if r.course_id == course_id
                                                     and (subject is None or r.learner_id == subject)}, key=str)
        dimensions = "|".join(map(str, (scope, course_id, subject, outcome, assessment, question, token)))
        documents.append(ARRDocument(
            id=uuid5(run_id, dimensions), run_id=run_id, course_id=course_id, scope=scope,
            subject_learner_id=subject, outcome_id=outcome, assessment_id=assessment, question_id=question,
            metrics=metrics, evidence_sets=evidence, evidence_ler_ids=used, dependency_ler_ids=dependencies,
            numerator=numerator, denominator=denominator,
            numerator_definition=numerator_definition, denominator_definition=denominator_definition,
            inclusion_rule="Phase 3 selected evidence; independent assessments and separate practice; observed input cohort",
            period=statistics.period, provenance=provenance, created_at=computed_at,
            interpretation_limits=InterpretationLimits(
                insufficient_evidence=insufficient, incomplete_coverage=incomplete, suppressed=suppressed,
                reasons=(["insufficient_evidence"] if insufficient else []) +
                        (["small_cohort_suppressed"] if suppressed else []) +
                        (["observed_input_not_enrollment"] if incomplete else []),
            ),
        ))

    for metric in statistics.student_outcomes:
        append("student_outcome", metric.course_id, metric, MetricEvidence(
            score_ler_ids=metric.score_ler_ids, error_ler_ids=metric.error_assessed_ler_ids,
            practice_ler_ids=metric.practice_ler_ids,
        ), subject=metric.learner_id, outcome=metric.outcome_id,
            numerator=metric.weighted_earned, denominator=metric.weighted_possible,
            numerator_definition="sum of selected weighted earned points",
            denominator_definition="sum of selected weighted possible points",
            insufficient=metric.insufficient_evidence)
    for metric in statistics.class_outcomes + statistics.assessment_questions:
        # Preserve assessment breakdowns inside their parent class ARR, not duplicate rows.
        count = metric.students_meeting_evidence_minimum
        mean = metric.mean_student_ratio
        append(metric.scope, metric.course_id, metric, MetricEvidence(cohort_ler_ids=metric.evidence_ler_ids),
               outcome=metric.outcome_id, assessment=metric.assessment_id, question=metric.question_id,
               numerator=Decimal(str(mean)) * count if mean is not None else None,
               denominator=count if mean is not None else None,
               numerator_definition="sum of sufficient student observed-performance ratios",
               denominator_definition="number of students meeting the configured evidence minimum",
               insufficient=metric.insufficient_evidence, suppressed=metric.suppressed)
    if clustering:
        if clustering.run_id != run_id or clustering.config != statistics.config:
            raise ValueError("clustering belongs to a different run/configuration")
        for partition in clustering.partitions:
            for group in partition.groups:
                if approved_clusters is not None and group.cluster_id not in approved_clusters:
                    continue
                if (statistics.config.suppress_small_cohorts
                        and group.unique_student_count < statistics.config.class_min_students):
                    # Detailed assignments stay in restricted run metadata, not published ARRs.
                    continue
                append("misconception_cluster", partition.course_id, ClusterResultMetrics(
                    group=group, assignments=[a for a in partition.assignments if a.cluster_id == group.cluster_id],
                    assessment_origin=partition.assessment_origin, assistance=partition.assistance,
                ), MetricEvidence(cluster_ler_ids=group.evidence_ler_ids), token=group.cluster_id)
    return sorted(documents, key=lambda document: str(document.id))
