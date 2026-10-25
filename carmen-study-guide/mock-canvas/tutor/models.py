"""Data shapes shared by the tutor modules. Database ids are Supabase uuids, as strings."""

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, Field


class Mode(StrEnum):
    """Assistance modes from spec §11.2, most restrictive first."""

    PROTECTED = "protected_assessment"
    GUIDED = "guided_homework"
    STUDY = "independent_study"


class Move(StrEnum):
    ASK = "ask"
    HINT = "hint"
    ANALOGOUS_EXAMPLE = "analogous_example"
    FEEDBACK = "feedback"
    EXPLANATION = "explanation"
    DECLINE = "decline"


@dataclass(frozen=True)
class Assessment:
    id: str
    code: str
    title: str
    integrity_status: str
    answers_released: bool
    text: str = ""  # question text, used only to spot pasted questions
    canvas_id: str | None = None


@dataclass(frozen=True)
class Learner:
    """Who is asking. Resolved server-side by the host app; never taken from the request body."""

    course_id: str
    learner_id: str
    pseudonym: str
    role: str = "student"


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    content: str
    doc_type: str
    page: int | None
    slide: int | None
    deep_link: str | None


@dataclass
class Session:
    id: str
    course_id: str
    learner_id: str
    assessment_id: str | None
    outcome_id: str | None
    mode: str = "independent_study"  # strictest mode the session has reached


@dataclass
class Turn:
    speaker: str  # student | tutor
    content: str
    hint_level: int | None = None


@dataclass
class PolicyDecision:
    mode: Mode
    reason: str
    assessment_id: str | None = None
    matched_codes: list[str] = field(default_factory=list)


class LeakVerdict(BaseModel):
    leaks: bool
    reason: str


class ReferenceVerdict(BaseModel):
    assessment_codes: list[str]


class TutorReply(BaseModel):
    """What the tutor model must return (structured output)."""

    message: str = Field(description="What the student sees. Plain text or light markdown.")
    move: Move = Field(description="The pedagogical move this reply makes.")
    hint_level: int = Field(description="0 when no hint is given; otherwise 1 (nudge) to 3 (strong hint).")
    cited_chunk_ids: list[str] = Field(description="Ids of the course_material blocks this reply relies on.")
    next_step: str = Field(description="One concrete thing the student should do next.")
