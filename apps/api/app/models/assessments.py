from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._mixins import SourceMixin

ASSESSMENT_KINDS = ("homework", "quiz", "exam")
QUESTION_TYPES = ("multiple_choice", "true_false", "numerical", "short_answer", "essay", "file")
ALIGNMENT_SOURCES = ("canvas_alignment", "instructor")


class AssignmentGroup(SourceMixin, Base):
    __tablename__ = "assignment_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    name: Mapped[str] = mapped_column(String(200))
    group_weight: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[int] = mapped_column(default=0)

    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="group", order_by="Assessment.position"
    )


class Assessment(SourceMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (CheckConstraint(f"kind IN {ASSESSMENT_KINDS}", name="ck_assessment_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    assignment_group_id: Mapped[int] = mapped_column(ForeignKey("assignment_groups.id"))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))
    points_possible: Mapped[float] = mapped_column(Float)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    submission_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    description_html: Mapped[str | None] = mapped_column(Text)
    module_label: Mapped[str | None] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(default=0)
    quiz_external_id: Mapped[str | None] = mapped_column(String(64))

    group: Mapped[AssignmentGroup] = relationship(back_populates="assessments")
    questions: Mapped[list["Question"]] = relationship(order_by="Question.position")
    rubric_criteria: Mapped[list["RubricCriterion"]] = relationship(
        order_by="RubricCriterion.position"
    )


class Question(SourceMixin, Base):
    """Parent rows hold a shared stem ("Q1"); leaf rows ("Q1a") are the scored items."""

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(f"question_type IN {QUESTION_TYPES}", name="ck_question_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    parent_question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"))
    label: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(default=0)
    prompt_html: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(30))
    points_possible: Mapped[float] = mapped_column(Float, default=0)
    answer_key: Mapped[Any] = mapped_column(JSON, nullable=True)
    choices: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # MC/TF options, not secret
    source_page: Mapped[int | None]

    outcomes: Mapped[list["QuestionOutcome"]] = relationship(back_populates="question")


class RubricCriterion(SourceMixin, Base):
    __tablename__ = "rubric_criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    description: Mapped[str] = mapped_column(String(300))
    long_description: Mapped[str | None] = mapped_column(Text)
    points: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(default=0)
    learning_outcome_id: Mapped[int | None] = mapped_column(ForeignKey("learning_outcomes.id"))


class QuestionOutcome(Base):
    __tablename__ = "question_outcomes"
    __table_args__ = (
        CheckConstraint(f"source IN {ALIGNMENT_SOURCES}", name="ck_question_outcome_source"),
    )

    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    outcome_id: Mapped[int] = mapped_column(ForeignKey("learning_outcomes.id"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(30))

    question: Mapped[Question] = relationship(back_populates="outcomes")
