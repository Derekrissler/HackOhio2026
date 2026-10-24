"""Adapt explicitly joined Supabase rows without parsing the extractor's payload.

The caller supplies an envelope of ler/response/question/attempt/assessment/practice
rows plus outcome_mappings, errors and evidence_ref_ids. No database calls occur here.
"""

from decimal import Decimal, InvalidOperation

from pydantic import AwareDatetime, TypeAdapter, ValidationError

from .contracts import AnalyticalInput, Contract


class InputIssue(Contract):
    field: str
    code: str


class AdapterResult(Contract):
    record: AnalyticalInput | None
    issues: list[InputIssue]


def adapt_ler(envelope: dict) -> AdapterResult:
    issues = []

    def issue(field, code):
        issues.append(InputIssue(field=field, code=code))

    if not isinstance(envelope, dict):
        return AdapterResult(record=None, issues=[InputIssue(field="envelope", code="invalid_object")])
    for key in ("ler", "response", "question", "attempt", "assessment", "practice"):
        if key in envelope and not isinstance(envelope[key], dict):
            issue(key, "invalid_object")
    if issues:
        return AdapterResult(record=None, issues=issues)

    def score(value, field, positive=False):
        if value is None:
            issue(field, "missing_score")
            return None
        try:
            if isinstance(value, bool):
                raise ValueError
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or (positive and number == 0):
                raise ValueError
            return number
        except (InvalidOperation, ValueError):
            issue(field, "invalid_score")
            return None

    ler = envelope.get("ler") or {}
    response = envelope.get("response") or {}
    question = envelope.get("question") or {}
    attempt = envelope.get("attempt") or {}
    assessment = envelope.get("assessment") or {}
    practice = envelope.get("practice") or {}
    # Reject inconsistent joins rather than borrowing evidence from another learner/course.
    relationships = [
        (response, "id", ler.get("response_id")),
        (question, "id", ler.get("question_id")),
        (attempt, "id", ler.get("attempt_id")),
        (assessment, "id", ler.get("assessment_id")),
        (practice, "id", ler.get("practice_attempt_id")),
        (response, "question_id", ler.get("question_id")),
        (response, "attempt_id", ler.get("attempt_id")),
        (question, "assessment_id", ler.get("assessment_id")),
        (attempt, "assessment_id", ler.get("assessment_id")),
    ]
    for row in (response, question, attempt, assessment, practice):
        relationships.append((row, "course_id", ler.get("course_id")))
    for row in (response, attempt, practice):
        relationships.append((row, "learner_id", ler.get("learner_id")))
    for row, key, expected in relationships:
        if key in row and row[key] != expected:
            issue(key, "inconsistent_join")
    if issues:
        return AdapterResult(record=None, issues=issues)

    earned = score(response.get("points_earned"), "points_earned")
    possible = score(question.get("points_possible"), "points_possible", positive=True)
    if earned is not None and possible is not None and earned > possible:
        issue("points_earned", "earned_exceeds_possible")
        earned = None

    timestamp = practice.get("created_at") if ler.get("assessment_origin") != "graded_canvas" else attempt.get("submitted_at")
    observed_at = None
    if timestamp is None:
        issue("observed_at", "missing_timestamp")
    else:
        try:
            observed_at = TypeAdapter(AwareDatetime).validate_python(timestamp)
        except ValidationError:
            issue("observed_at", "invalid_timestamp")

    # Vocabulary must be confirmed by the upstream team. Unrecognized values stay unknown.
    assistance = ler.get("assistance_level")
    if assistance not in ("independent", "assisted"):
        assistance = "unknown"
        issue("assistance", "unknown_assistance")

    fields = (
        "schema_version", "course_id", "learner_id", "assessment_id", "question_id",
        "attempt_id", "response_id", "practice_attempt_id", "revision", "is_current",
        "assessment_origin", "hints_used", "independent_correctness", "analysis_status",
    )
    data = {key: ler[key] for key in fields if key in ler}
    data.update(
        ler_id=ler.get("id"), assessment_type=assessment.get("assessment_type"),
        question_type=question.get("question_type"), attempt_number=attempt.get("attempt_number"),
        observed_at=observed_at, points_earned=earned, points_possible=possible,
        assistance=assistance, outcome_mappings=envelope.get("outcome_mappings", []),
        errors=envelope.get("errors", []), errors_analyzed=envelope.get("errors_analyzed"),
        evidence_ref_ids=envelope.get("evidence_ref_ids", []),
    )
    try:
        record = AnalyticalInput.model_validate(data)
    except ValidationError as exc:
        # Do not return raw values, instructor text, student responses, or Pydantic input dumps.
        for error in exc.errors(include_input=False, include_context=False, include_url=False):
            issue(".".join(map(str, error["loc"])) or "record", error["type"])
        return AdapterResult(record=None, issues=issues)
    if not record.is_current:
        issue("is_current", "superseded_ler")
    if record.analysis_status == "insufficient":
        issue("analysis_status", "insufficient_analysis")
    return AdapterResult(record=record, issues=issues)
