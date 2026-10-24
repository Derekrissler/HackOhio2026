from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from tests.conftest import ISE_COURSE, STAT_COURSE


def count(db: Session, table) -> int:
    return db.scalar(select(func.count()).select_from(table))


def test_row_counts(db):
    assert count(db, m.User) == 21
    assert count(db, m.Course) == 2
    assert count(db, m.Assessment) == 9
    assert count(db, m.Question) == 57  # 42 ISE leaves + 10 parent stems + 5 STAT
    assert count(db, m.Submission) == 146  # 7 × 20 + 2 × 3
    assert count(db, m.CourseMaterial) == 12
    assert count(db, m.File) == 80


def test_demo_ids_are_stable(db):
    names = {u.id: u.name for u in db.scalars(select(m.User).where(m.User.id <= 4))}
    assert names == {1: "Prof. Dana Rivera", 2: "Alex Kim", 3: "Priya Natarajan", 4: "Marcus Bell"}
    assert db.get(m.Course, STAT_COURSE).code == "STAT 1450"
    assert db.get(m.Course, ISE_COURSE).code == "ISE 3200"


def test_graded_scores_equal_the_sum_of_question_points(db):
    graded = db.scalars(
        select(m.Submission).where(m.Submission.workflow_state == "graded", m.Submission.excused.is_(False))
    ).all()
    assert graded
    for sub in graded:
        if sub.missing:
            assert sub.score == 0
            continue
        assert sum(r.points_awarded or 0 for r in sub.responses) == sub.score, sub.id


def test_scanned_midterm_responses_are_manual_entries_without_text(db):
    midterm = db.scalar(select(m.Assessment).where(m.Assessment.title == "Midterm Exam"))
    responses = db.scalars(
        select(m.QuestionResponse).join(m.Submission).where(m.Submission.assessment_id == midterm.id)
    ).all()
    assert len(responses) == 200  # 20 students × 10 parts
    assert {r.graded_by for r in responses} == {"manual_entry"}
    assert all(r.response is None for r in responses)
    scans = db.scalars(select(m.File).where(m.File.filename.like("midterm_scan_%"))).all()
    assert len(scans) == 20 and not any(f.has_text_layer for f in scans)


def test_alignments_are_instructor_or_canvas_only(db):
    sources = set(db.scalars(select(m.QuestionOutcome.source)))
    assert sources <= {"canvas_alignment", "instructor"}
    # every scored ISE question has 1–2 outcomes
    leaves = db.scalars(
        select(m.Question).join(m.Assessment).where(
            m.Assessment.course_id == ISE_COURSE,
            ~m.Question.id.in_(select(m.Question.parent_question_id).where(m.Question.parent_question_id.isnot(None))),
        )
    ).all()
    assert len(leaves) == 42
    assert all(1 <= len(q.outcomes) <= 2 for q in leaves)


def test_rubric_criteria_carry_canvas_outcome_alignment(db):
    criteria = db.scalars(select(m.RubricCriterion)).all()
    assert len(criteria) == 6
    assert all(c.learning_outcome_id for c in criteria)


def test_teacher_only_notes_are_hidden(db):
    hidden = db.scalars(select(m.Feedback).where(m.Feedback.visible_to_student.is_(False))).all()
    assert len(hidden) == 3
