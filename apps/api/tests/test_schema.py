from datetime import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import (
    Assessment,
    AssignmentGroup,
    Question,
    QuestionOutcome,
    QuestionResponse,
    Submission,
    LearningOutcome,
)

EXPECTED_TABLES = {
    "users",
    "courses",
    "enrollments",
    "learning_outcomes",
    "assignment_groups",
    "assessments",
    "questions",
    "rubric_criteria",
    "question_outcomes",
    "submissions",
    "question_responses",
    "rubric_scores",
    "feedback",
    "files",
    "course_materials",
}


def test_exactly_the_phase3_tables_exist(db):
    assert set(inspect(db.get_bind()).get_table_names()) == EXPECTED_TABLES


@pytest.fixture
def question(db):
    group = AssignmentGroup(course_id=1, name="Homework", group_weight=30)
    db.add(group)
    db.flush()
    assessment = Assessment(
        course_id=1, assignment_group_id=group.id, title="HW", kind="homework", points_possible=10
    )
    db.add(assessment)
    db.flush()
    q = Question(
        assessment_id=assessment.id, label="Q1", prompt_html="p", question_type="essay", points_possible=10
    )
    outcome = LearningOutcome(course_id=1, code="LO1", title="Formulate")
    db.add_all([q, outcome])
    db.flush()
    return q, outcome


def test_question_outcome_rejects_ai_source(db, question):
    q, outcome = question
    db.add(QuestionOutcome(question_id=q.id, outcome_id=outcome.id, source="ai"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_question_outcome_accepts_instructor_source(db, question):
    q, outcome = question
    db.add(QuestionOutcome(question_id=q.id, outcome_id=outcome.id, source="instructor"))
    db.flush()


def test_one_response_per_question_per_submission(db, question):
    q, _ = question
    sub = Submission(
        assessment_id=q.assessment_id, user_id=2, workflow_state="graded", submitted_at=datetime(2026, 9, 1)
    )
    db.add(sub)
    db.flush()
    for _ in range(2):
        db.add(QuestionResponse(submission_id=sub.id, question_id=q.id, points_possible=10, graded_by="instructor"))
    with pytest.raises(IntegrityError):
        db.flush()
