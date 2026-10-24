from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._mixins import SourceMixin

WORKFLOW_STATES = ("unsubmitted", "submitted", "graded")
GRADED_BY = ("canvas_auto", "instructor", "manual_entry")
FEEDBACK_KINDS = ("submission_comment", "question_comment", "rubric_comment")


class Submission(SourceMixin, Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "user_id", "attempt"),
        CheckConstraint(f"workflow_state IN {WORKFLOW_STATES}", name="ck_submission_state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    attempt: Mapped[int] = mapped_column(default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime)
    score: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str | None] = mapped_column(String(20))
    excused: Mapped[bool] = mapped_column(Boolean, default=False)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    missing: Mapped[bool] = mapped_column(Boolean, default=False)
    workflow_state: Mapped[str] = mapped_column(String(20))
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"))

    responses: Mapped[list["QuestionResponse"]] = relationship()
    rubric_scores: Mapped[list["RubricScore"]] = relationship()
    feedback: Mapped[list["Feedback"]] = relationship(order_by="Feedback.created_at")


class QuestionResponse(Base):
    __tablename__ = "question_responses"
    __table_args__ = (
        UniqueConstraint("submission_id", "question_id"),
        CheckConstraint(f"graded_by IN {GRADED_BY}", name="ck_response_graded_by"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    response: Mapped[Any] = mapped_column(JSON, nullable=True)
    points_awarded: Mapped[float | None] = mapped_column(Float)
    points_possible: Mapped[float] = mapped_column(Float)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    graded_by: Mapped[str] = mapped_column(String(20))


class RubricScore(Base):
    __tablename__ = "rubric_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    criterion_id: Mapped[int] = mapped_column(ForeignKey("rubric_criteria.id"))
    points: Mapped[float | None] = mapped_column(Float)
    comment: Mapped[str | None] = mapped_column(Text)


class Feedback(SourceMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint(f"kind IN {FEEDBACK_KINDS}", name="ck_feedback_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    question_response_id: Mapped[int | None] = mapped_column(ForeignKey("question_responses.id"))
    rubric_score_id: Mapped[int | None] = mapped_column(ForeignKey("rubric_scores.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    visible_to_student: Mapped[bool] = mapped_column(Boolean, default=True)
