"""One test per visibility rule in docs/superpowers/plans/2026-10-24-phase3.md §2."""

from datetime import datetime

import pytest
from sqlalchemy import select

from app import models as m
from app.clock import get_now
from app.main import app
from tests.conftest import (
    ALEX_ID,
    ISE_COURSE,
    JORDAN_ID,
    MARCUS_ID,
    PRIYA_ID,
    STAT_COURSE,
    STUDENT,
    TEACHER,
    as_user,
)

ALEX, MARCUS, PRIYA, JORDAN = (as_user(i) for i in (ALEX_ID, MARCUS_ID, PRIYA_ID, JORDAN_ID))


@pytest.fixture(autouse=True)
def frozen_clock():
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 24, 16, 0)
    yield
    app.dependency_overrides.pop(get_now, None)


def assessment_id(db, title_prefix: str) -> int:
    return db.scalar(select(m.Assessment.id).where(m.Assessment.course_id == ISE_COURSE,
                                                    m.Assessment.title.startswith(title_prefix)))


def submission_id(db, title_prefix: str, user_id: int) -> int:
    return db.scalar(
        select(m.Submission.id).where(
            m.Submission.assessment_id == assessment_id(db, title_prefix), m.Submission.user_id == user_id
        )
    )


def base(course: int = ISE_COURSE) -> str:
    return f"/api/courses/{course}"


# -- identity ----------------------------------------------------------------------------------

def test_cookie_identifies_the_user_when_no_header(client):
    client.cookies.set("demo_user", str(ALEX_ID))
    assert client.get("/api/me").json()["name"] == "Alex Kim"


def test_header_wins_over_cookie(client):
    client.cookies.set("demo_user", str(ALEX_ID))
    assert client.get("/api/me", headers=TEACHER).json()["name"] == "Prof. Dana Rivera"


def test_demo_users_include_role_and_sortable_name(client):
    users = client.get("/api/demo/users").json()
    assert users[0] == {"id": 1, "name": "Prof. Dana Rivera", "sortable_name": "Rivera, Dana", "role_summary": "Teacher"}
    students = [u["sortable_name"] for u in users[1:]]
    assert students == sorted(students)


# -- submissions -------------------------------------------------------------------------------

def test_student_can_read_own_submission(client, db):
    sid = submission_id(db, "HW1", ALEX_ID)
    assert client.get(f"{base()}/submissions/{sid}", headers=ALEX).status_code == 200


def test_student_gets_404_for_another_students_submission(client, db):
    sid = submission_id(db, "HW1", PRIYA_ID)
    assert client.get(f"{base()}/submissions/{sid}", headers=ALEX).status_code == 404


def test_teacher_can_read_any_submission(client, db):
    sid = submission_id(db, "HW1", PRIYA_ID)
    assert client.get(f"{base()}/submissions/{sid}", headers=TEACHER).status_code == 200


def test_submission_must_belong_to_the_course_in_the_url(client, db):
    sid = submission_id(db, "HW1", ALEX_ID)  # an ISE submission
    assert client.get(f"{base(STAT_COURSE)}/submissions/{sid}", headers=ALEX).status_code == 404


def test_submission_list_is_teacher_only(client, db):
    aid = assessment_id(db, "HW1")
    assert client.get(f"{base()}/assessments/{aid}/submissions", headers=ALEX).status_code == 403
    rows = client.get(f"{base()}/assessments/{aid}/submissions", headers=TEACHER).json()
    assert len(rows) == 20


# -- files -------------------------------------------------------------------------------------

def _submission_file(db, title_prefix: str, user_id: int) -> int:
    return db.get(m.Submission, submission_id(db, title_prefix, user_id)).file_id


def test_student_can_open_own_submission_pdf(client, db):
    res = client.get(f"/api/files/{_submission_file(db, 'Midterm', ALEX_ID)}/content", headers=ALEX)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("inline")


def test_student_gets_404_for_another_students_pdf(client, db):
    res = client.get(f"/api/files/{_submission_file(db, 'Midterm', PRIYA_ID)}/content", headers=ALEX)
    assert res.status_code == 404


def test_course_material_requires_enrollment(client, db):
    stat_file = db.scalar(select(m.CourseMaterial.file_id).where(m.CourseMaterial.course_id == STAT_COURSE))
    assert client.get(f"/api/files/{stat_file}/content", headers=ALEX).status_code == 200
    assert client.get(f"/api/files/{stat_file}/content", headers=JORDAN).status_code == 403


def test_pdf_iframe_works_with_cookie_only(client, db):
    client.cookies.set("demo_user", str(ALEX_ID))
    assert client.get(f"/api/files/{_submission_file(db, 'HW1', ALEX_ID)}/content").status_code == 200


# -- questions and answer keys -----------------------------------------------------------------

def test_student_sees_no_questions_for_an_untaken_quiz(client, db):
    body = client.get(f"{base()}/assessments/{assessment_id(db, 'Quiz 3')}", headers=ALEX).json()
    assert body["questions"] is None
    assert body["questions_hidden_reason"]


def test_teacher_sees_questions_and_keys_for_an_untaken_quiz(client, db):
    body = client.get(f"{base()}/assessments/{assessment_id(db, 'Quiz 3')}", headers=TEACHER).json()
    assert len(body["questions"]) == 5
    assert all(q["answer_key"] is not None for q in body["questions"])
    assert all(q["outcomes"] for q in body["questions"])


def test_student_sees_homework_questions_but_no_key_before_grading(client, db):
    body = client.get(f"{base()}/assessments/{assessment_id(db, 'HW3')}", headers=ALEX).json()
    assert len(body["questions"]) == 7  # 5 parts + 2 stems
    assert all(q["answer_key"] is None for q in body["questions"])
    assert all(q["outcomes"] == [] for q in body["questions"])


def test_student_sees_keys_once_graded(client, db):
    body = client.get(f"{base()}/assessments/{assessment_id(db, 'Quiz 1')}", headers=ALEX).json()
    assert all(q["answer_key"] is not None for q in body["questions"])


def test_ungraded_own_submission_hides_scores_keys_and_comments(client, db):
    sid = submission_id(db, "HW3", ALEX_ID)  # submitted early, not graded
    body = client.get(f"{base()}/submissions/{sid}", headers=ALEX).json()
    assert body["workflow_state"] == "submitted"
    assert body["results_visible"] is False
    assert body["score"] is None
    assert body["responses"]  # own answers are visible
    assert all(r["points_awarded"] is None and r["answer_key"] is None and r["is_correct"] is None
               for r in body["responses"])
    assert body["comments"] == [] and body["rubric"] == []


def test_graded_quiz_shows_own_answers_correctness_and_comments(client, db):
    sid = submission_id(db, "Quiz 1", ALEX_ID)
    body = client.get(f"{base()}/submissions/{sid}", headers=ALEX).json()
    assert body["results_visible"] is True
    assert len(body["responses"]) == 5
    assert all(r["answer_key"] is not None and r["is_correct"] is not None for r in body["responses"])


# -- teacher-only comments ---------------------------------------------------------------------

PRIVATE = "Spoke with Marcus after class"


def test_teacher_only_comment_never_reaches_the_student(client, db):
    sid = submission_id(db, "Midterm", MARCUS_ID)
    for url in (f"{base()}/submissions/{sid}", f"{base()}/users/{MARCUS_ID}/grades", f"{base()}/home"):
        assert PRIVATE not in client.get(url, headers=MARCUS).text, url


def test_teacher_sees_teacher_only_comment_flagged(client, db):
    sid = submission_id(db, "Midterm", MARCUS_ID)
    comments = client.get(f"{base()}/submissions/{sid}", headers=TEACHER).json()["comments"]
    private = [c for c in comments if c["text"].startswith(PRIVATE)]
    assert len(private) == 1 and private[0]["visible_to_student"] is False


# -- grades ------------------------------------------------------------------------------------

def test_student_can_read_own_grades(client):
    body = client.get(f"{base()}/users/{ALEX_ID}/grades", headers=ALEX).json()
    assert body["current_percent"] == pytest.approx(82.111, abs=1e-3)
    hw3 = next(r for r in body["rows"] if r["title"].startswith("HW3"))
    assert hw3["score"] is None and hw3["workflow_state"] == "submitted"


def test_student_gets_404_for_another_students_grades(client):
    assert client.get(f"{base()}/users/{PRIYA_ID}/grades", headers=ALEX).status_code == 404


def test_teacher_can_read_any_students_grades(client):
    assert client.get(f"{base()}/users/{PRIYA_ID}/grades", headers=TEACHER).status_code == 200


def test_gradebook_is_teacher_only(client):
    assert client.get(f"{base()}/gradebook", headers=ALEX).status_code == 403
    body = client.get(f"{base()}/gradebook", headers=TEACHER).json()
    assert len(body["students"]) == 20 and len(body["assessments"]) == 7


# -- lists that mix everyone's data ------------------------------------------------------------

def test_assignment_list_shows_only_own_status(client, db):
    groups = client.get(f"{base()}/assignment_groups", headers=ALEX).json()
    hw1 = next(a for g in groups for a in g["assessments"] if a["title"].startswith("HW1"))
    assert hw1["my_submission"]["score"] == 32
    assert "submission_counts" not in hw1 or hw1["submission_counts"] is None


def test_home_upcoming_and_recent_feedback(client):
    body = client.get(f"{base()}/home", headers=STUDENT).json()
    assert [a["title"][:4] for a in body["upcoming"]] == ["HW3:", "Quiz"]
    assert body["recent_feedback"]
    assert all(f["visible_to_student"] for f in body["recent_feedback"])
