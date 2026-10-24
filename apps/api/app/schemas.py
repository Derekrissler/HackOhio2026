"""Response DTOs shared by the routers. Mirrored by apps/web/src/api/types.ts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EnrollmentOut(BaseModel):
    course_id: int
    role: str


class MeOut(BaseModel):
    id: int
    name: str
    email: str | None
    enrollments: list[EnrollmentOut]


class DemoUserOut(BaseModel):
    id: int
    name: str
    sortable_name: str
    role_summary: str


class CourseOut(BaseModel):
    id: int
    code: str
    name: str
    term: str | None
    role: str


class AnalyticsSummaryOut(BaseModel):
    course_id: int
    status: str


# -- shared pieces -------------------------------------------------------------------------------

class FeedbackOut(BaseModel):
    id: int
    kind: str
    author_name: str
    text: str
    created_at: datetime
    visible_to_student: bool


class MySubmissionOut(BaseModel):
    """The caller's own submission state in lists (students only)."""

    id: int
    workflow_state: str
    score: float | None  # None until graded
    submitted_at: datetime | None
    late: bool
    missing: bool
    excused: bool


class SubmissionCountsOut(BaseModel):
    """Teacher-only summary in lists."""

    submitted: int
    graded: int
    total: int


class AssessmentSummaryOut(BaseModel):
    id: int
    title: str
    kind: str
    group_id: int
    points_possible: float
    due_at: datetime | None
    module_label: str | None
    my_submission: MySubmissionOut | None = None
    submission_counts: SubmissionCountsOut | None = None


class AssignmentGroupOut(BaseModel):
    id: int
    name: str
    weight: float
    assessments: list[AssessmentSummaryOut]


# -- assessment detail ---------------------------------------------------------------------------

class OutcomeRefOut(BaseModel):
    id: int
    code: str
    title: str


class QuestionOut(BaseModel):
    id: int
    label: str
    parent_id: int | None
    position: int
    prompt_html: str
    question_type: str
    points_possible: float
    choices: list[str] | None
    answer_key: Any = None  # None unless results are visible to the caller
    outcomes: list[OutcomeRefOut]  # teacher only; [] for students
    source_page: int | None


class RubricCriterionOut(BaseModel):
    id: int
    description: str
    long_description: str | None
    points: float
    outcome: OutcomeRefOut | None


class AssessmentDetailOut(BaseModel):
    id: int
    title: str
    kind: str
    group_name: str
    group_weight: float
    points_possible: float
    due_at: datetime | None
    module_label: str | None
    description_html: str | None
    submission_types: list[str]
    questions: list[QuestionOut] | None
    questions_hidden_reason: str | None
    rubric: list[RubricCriterionOut]
    my_submission: MySubmissionOut | None


class SubmissionRowOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    sortable_name: str
    workflow_state: str
    score: float | None
    submitted_at: datetime | None
    late: bool
    missing: bool
    excused: bool


# -- submission detail ---------------------------------------------------------------------------

class FileRefOut(BaseModel):
    id: int
    display_name: str
    mime: str
    page_count: int | None
    has_text_layer: bool
    url: str


class ResponseOut(BaseModel):
    question_id: int
    label: str
    parent_label: str | None
    prompt_html: str
    question_type: str
    choices: list[str] | None
    response: Any
    points_awarded: float | None
    points_possible: float
    is_correct: bool | None
    answer_key: Any
    graded_by: str
    source_page: int | None
    comments: list[FeedbackOut]


class RubricScoreOut(BaseModel):
    criterion_id: int
    description: str
    points: float | None
    points_possible: float
    comment: str | None


class SubmissionDetailOut(BaseModel):
    id: int
    assessment: AssessmentSummaryOut
    user_id: int
    user_name: str
    workflow_state: str
    submitted_at: datetime | None
    graded_at: datetime | None
    score: float | None
    late: bool
    missing: bool
    excused: bool
    results_visible: bool
    file: FileRefOut | None
    responses: list[ResponseOut]
    rubric: list[RubricScoreOut]
    comments: list[FeedbackOut]


# -- grades --------------------------------------------------------------------------------------

class GroupGradeOut(BaseModel):
    id: int
    name: str
    weight: float
    earned: float
    possible: float
    percent: float | None


class GradeRowOut(BaseModel):
    assessment_id: int
    title: str
    kind: str
    group_id: int
    due_at: datetime | None
    points_possible: float
    submission_id: int | None
    workflow_state: str
    score: float | None
    late: bool
    missing: bool
    excused: bool
    comments: list[FeedbackOut]
    rubric: list[RubricScoreOut]


class GradesOut(BaseModel):
    user_id: int
    user_name: str
    weighted: bool
    current_percent: float | None
    groups: list[GroupGradeOut]
    rows: list[GradeRowOut]


class GradebookCellOut(BaseModel):
    submission_id: int | None
    workflow_state: str
    score: float | None
    late: bool
    missing: bool
    excused: bool


class GradebookStudentOut(BaseModel):
    id: int
    name: str
    sortable_name: str
    current_percent: float | None
    cells: list[GradebookCellOut]  # aligned with GradebookOut.assessments


class GradebookOut(BaseModel):
    assessments: list[AssessmentSummaryOut]
    students: list[GradebookStudentOut]


# -- course pages --------------------------------------------------------------------------------

class OutcomeOut(BaseModel):
    id: int
    code: str
    title: str
    description: str | None


class SyllabusOut(BaseModel):
    syllabus_html: str | None
    outcomes: list[OutcomeOut]
    summary: list[AssessmentSummaryOut]  # all assessments, by due date


class RecentFeedbackOut(FeedbackOut):
    submission_id: int
    assessment_title: str


class NeedsGradingOut(BaseModel):
    assessment_id: int
    title: str
    count: int


class HomeOut(BaseModel):
    course: CourseOut
    upcoming: list[AssessmentSummaryOut]
    recent_feedback: list[RecentFeedbackOut]  # students
    needs_grading: list[NeedsGradingOut]  # teachers


class MaterialOut(BaseModel):
    id: int
    title: str
    kind: str
    file: FileRefOut


class ModuleOut(BaseModel):
    label: str
    position: int
    materials: list[MaterialOut]
