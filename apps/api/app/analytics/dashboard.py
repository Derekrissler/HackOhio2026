"""Authorized, display-only analytics. No writes and no private manifests in HTTP DTOs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .evidence_repository import RepositoryError, read_pages


class AnalyticsCourseOut(BaseModel):
    id: UUID
    code: str
    title: str
    canvas_id: str | None = None
    role: Literal["student", "instructor", "ta"]


class ErrorPatternOut(BaseModel):
    code: str
    occurrence_count: int | None = None
    affected_students: int | None = None
    assessed_students: int | None = None
    prevalence: float | None = None
    recurring: bool | None = None


class PerformanceOut(BaseModel):
    id: UUID
    scope: Literal["class_outcome", "assessment_question", "student_outcome"]
    outcome_id: UUID | None = None
    assessment_id: UUID | None = None
    question_id: UUID | None = None
    label: str
    mean_student_ratio: float | None = None
    pooled_score_ratio: float | None = None
    observed_score_ratio: float | None = None
    eligible_students: int | None = None
    assessed_students: int | None = None
    evidence_coverage_ratio: float | None = None
    score_observations: int | None = None
    evidence_count: int | None = None
    insufficient_evidence: bool
    suppressed: bool
    errors: list[ErrorPatternOut] = Field(default_factory=list)
    error_classification_observations: int | None = None


class ClusterOut(BaseModel):
    id: UUID
    error_code: str
    unique_students: int
    evidence_count: int
    assessment_origin: str
    assistance: str
    interpretation_limit: str
    representative_text: str | None = None


class AnalyticsDashboardOut(BaseModel):
    course_id: UUID
    status: Literal["ready", "no_results", "stale", "incomplete", "insufficient_evidence"]
    run_id: UUID | None = None
    computed_at: datetime | None = None
    performance: list[PerformanceOut] = Field(default_factory=list)
    clusters: list[ClusterOut] = Field(default_factory=list)
    interpretation: str = (
        "Descriptive performance on observed evidence, not a mastery estimate. "
        "Coverage refers to observed assessment evidence, not course enrollment. "
        "Practice is kept separate from independent assessment scores."
    )


def load_dashboard(user_client, control_factory, course_id, *, learner_id=None, run_id=None):
    """RLS-scoped discovery precedes privileged freshness checks.

    Select the newest visible run, including stale rows; never silently fall back
    to an older result when the newest visible run is stale or incomplete.
    Student scope is additionally narrowed to the identity from the verified JWT.
    """
    from .repository import SupabaseARRReader
    from .service import retrieve_current_results

    filters = {"course_id": str(course_id), "schema_version": "1.1"}
    if learner_id is not None:
        filters.update(scope="student_outcome", subject_learner_id=str(learner_id))
    if run_id is not None:
        filters["run_id"] = str(run_id)
    rows = read_pages(user_client, "analytics_results", "id,run_id,created_at,is_stale", filters=filters)
    result = AnalyticsDashboardOut(course_id=course_id, status="no_results")
    if not rows:
        return result
    try:
        newest = max(rows, key=lambda row: (datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")), row["run_id"]))
        selected = UUID(newest["run_id"])
    except (ValueError, TypeError, KeyError):
        raise RepositoryError("invalid_stored_arr") from None
    result.run_id = selected
    if any(row["is_stale"] for row in rows if row["run_id"] == str(selected)):
        result.status = "stale"
        return result
    control = control_factory()
    run = control.get_run(selected)
    if not run or run["course_id"] != str(course_id) or run["params"].get("status") != "complete":
        result.status = "incomplete"
        return result
    try:
        documents = retrieve_current_results(
            control, SupabaseARRReader(user_client), course_id, selected,
            scope="student_outcome" if learner_id is not None else None, learner_id=learner_id,
        )
    except RepositoryError as exc:
        if str(exc) != "analysis_run_is_stale":
            raise
        result.status = "stale"
        return result
    if not documents:
        result.status = "incomplete"
        return result
    # Recheck publication flags after retrieval, closing ordinary stale-flag races.
    after = read_pages(user_client, "analytics_results", "id,is_stale", filters=filters | {"run_id": str(selected)})
    before_ids = {row["id"] for row in rows if row["run_id"] == str(selected)}
    if {row["id"] for row in after} != before_ids or any(row["is_stale"] for row in after):
        result.status = "stale"
        return result
    labels = {}
    for table, column in (("outcomes", "code"), ("questions", "code")):
        labels[table] = {row["id"]: row[column] for row in read_pages(
            user_client, table, f"id,{column}", filters={"course_id": str(course_id)},
        )}
    for doc in documents:
        metric = doc.metrics
        if learner_id is not None:
            if doc.scope != "student_outcome" or doc.subject_learner_id != learner_id:
                raise RepositoryError("unexpected_student_scope")
        elif doc.scope == "student_outcome":
            continue  # Instructor summary does not enumerate individual learners.
        if doc.scope == "misconception_cluster":
            approved = doc.provenance.get("cluster_review", {}).get("approved") is True
            if not approved:
                continue
            result.clusters.append(ClusterOut(
                id=doc.id, error_code=metric.group.representative_error_code,
                unique_students=metric.group.unique_student_count,
                evidence_count=metric.group.evidence_observation_count,
                assessment_origin=metric.assessment_origin, assistance=metric.assistance,
                interpretation_limit=metric.group.interpretation_limit,
                representative_text=metric.group.representative_text,
            ))
            continue
        student = doc.scope == "student_outcome"
        suppressed = doc.interpretation_limits.suppressed
        dimension = doc.outcome_id if doc.outcome_id else doc.question_id
        label = labels["outcomes" if doc.outcome_id else "questions"].get(str(dimension), str(dimension))
        result.performance.append(PerformanceOut(
            id=doc.id, scope=doc.scope, outcome_id=doc.outcome_id,
            assessment_id=doc.assessment_id, question_id=doc.question_id, label=label,
            mean_student_ratio=None if student else metric.mean_student_ratio,
            pooled_score_ratio=None if student else metric.pooled_score_ratio,
            observed_score_ratio=metric.observed_score_ratio if student else None,
            eligible_students=None if student else metric.students_meeting_evidence_minimum,
            assessed_students=None if student else metric.assessed_student_count,
            evidence_coverage_ratio=None if student else metric.evidence_coverage_ratio,
            score_observations=metric.scored_observation_count if student else None,
            evidence_count=None if suppressed else len(doc.evidence_ler_ids),
            insufficient_evidence=doc.interpretation_limits.insufficient_evidence, suppressed=suppressed,
            error_classification_observations=metric.error_assessed_observation_count if student else None,
            errors=[] if suppressed else (
                [ErrorPatternOut(code=e.code, occurrence_count=e.occurrence_count, recurring=e.recurring) for e in metric.errors] if student else
                [ErrorPatternOut(code=e.code, affected_students=e.numerator, assessed_students=e.denominator, prevalence=e.prevalence)
                 for e in metric.error_prevalence if not e.suppressed]),
        ))
    result.performance.sort(key=lambda row: (row.scope, row.label, str(row.id)))
    result.status = "ready" if result.clusters or any(
        not row.suppressed and not row.insufficient_evidence for row in result.performance
    ) else "insufficient_evidence"
    result.computed_at = max(doc.created_at for doc in documents)
    return result
