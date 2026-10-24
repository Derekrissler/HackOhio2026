"""The canonical course model every adapter produces and the loader consumes.

References between objects use *external ids* (strings), never database ids, so adapters stay
independent of the database and re-ingesting the same source is idempotent.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["student", "teacher"]


class CUser(BaseModel):
    external_id: str
    name: str
    sortable_name: str
    email: str | None = None


class CEnrollment(BaseModel):
    external_id: str
    user: str
    role: Role


class CCourse(BaseModel):
    external_id: str
    code: str
    name: str
    term: str | None = None
    syllabus_html: str | None = None
    apply_group_weights: bool = False
    start_at: datetime | None = None
    end_at: datetime | None = None


class COutcome(BaseModel):
    external_id: str
    code: str
    title: str
    description: str | None = None
    position: int = 0


class CGroup(BaseModel):
    external_id: str
    name: str
    weight: float = 0
    position: int = 0


class CQuestion(BaseModel):
    external_id: str
    parent: str | None = None
    label: str
    position: int
    prompt_html: str
    question_type: str
    points_possible: float
    answer_key: Any = None
    choices: list[str] | None = None
    source_page: int | None = None
    source: Literal["canvas", "manual"] = "canvas"


class CRubricCriterion(BaseModel):
    external_id: str
    description: str
    long_description: str | None = None
    points: float
    position: int
    outcome: str | None = None


class CAssessment(BaseModel):
    external_id: str
    group: str
    title: str
    kind: Literal["homework", "quiz", "exam"]
    points_possible: float
    due_at: datetime | None = None
    submission_types: list[str] = Field(default_factory=list)
    description_html: str | None = None
    module_label: str | None = None
    position: int = 0
    quiz_external_id: str | None = None
    questions: list[CQuestion] = Field(default_factory=list)
    rubric: list[CRubricCriterion] = Field(default_factory=list)


class CFile(BaseModel):
    external_id: str
    owner: str | None = None
    display_name: str
    filename: str
    mime: str
    storage_path: str  # relative to <repo>/data/
    size: int
    sha256: str = ""
    page_count: int | None = None
    has_text_layer: bool = True


class CMaterial(BaseModel):
    external_id: str
    file: str
    title: str
    kind: Literal["lecture", "slides", "reading", "exam"] = "reading"
    module_label: str | None = None
    module_position: int = 0
    position: int = 0


class CResponse(BaseModel):
    question: str
    response: Any = None
    points_awarded: float | None = None
    is_correct: bool | None = None
    graded_by: Literal["canvas_auto", "instructor", "manual_entry"]


class CRubricScore(BaseModel):
    criterion: str
    points: float | None
    comment: str | None = None


class CFeedback(BaseModel):
    external_id: str
    author: str
    kind: Literal["submission_comment", "question_comment", "rubric_comment"]
    text: str
    created_at: datetime
    attempt: int = 1
    visible_to_student: bool = True
    question: str | None = None  # for question comments
    source: Literal["canvas", "manual"] = "canvas"


class CSubmission(BaseModel):
    external_id: str
    assessment: str
    user: str
    attempt: int = 1
    submitted_at: datetime | None = None
    graded_at: datetime | None = None
    score: float | None = None
    grade: str | None = None
    excused: bool = False
    late: bool = False
    missing: bool = False
    workflow_state: Literal["unsubmitted", "submitted", "graded"]
    file: str | None = None
    responses: list[CResponse] = Field(default_factory=list)
    rubric_scores: list[CRubricScore] = Field(default_factory=list)
    feedback: list[CFeedback] = Field(default_factory=list)


class CAlignment(BaseModel):
    question: str
    outcome: str
    weight: float = 1.0
    source: Literal["canvas_alignment", "instructor"]


class CourseBundle(BaseModel):
    course: CCourse
    users: list[CUser] = Field(default_factory=list)
    enrollments: list[CEnrollment] = Field(default_factory=list)
    outcomes: list[COutcome] = Field(default_factory=list)
    groups: list[CGroup] = Field(default_factory=list)
    assessments: list[CAssessment] = Field(default_factory=list)
    files: list[CFile] = Field(default_factory=list)
    materials: list[CMaterial] = Field(default_factory=list)
    submissions: list[CSubmission] = Field(default_factory=list)
    alignments: list[CAlignment] = Field(default_factory=list)
    capabilities: set[str] = Field(default_factory=set)
