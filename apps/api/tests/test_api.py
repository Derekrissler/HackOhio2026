import pytest
from sqlalchemy.orm import Session

from app.models import Course, Enrollment
from tests.conftest import STUDENT, TEACHER


def test_health_needs_no_auth(client):
    assert client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_me_rejects_missing_invalid_or_unknown_user(client, headers):
    assert client.get("/api/me", headers=headers).status_code == 401


def test_me_returns_user_and_enrollments(client):
    body = client.get("/api/me", headers=STUDENT).json()
    assert body["name"] == "Alex Kim"
    assert body["enrollments"] == [{"course_id": 1, "role": "student"}]


def test_demo_users_lists_everyone_without_auth(client):
    users = client.get("/api/demo/users").json()
    assert [u["id"] for u in users] == [1, 2, 3, 4]
    assert users[0]["role_summary"] == "Teacher"
    assert users[1]["role_summary"] == "Student"


def test_courses_lists_callers_courses_with_role(client):
    assert client.get("/api/courses", headers=TEACHER).json() == [
        {
            "id": 1,
            "code": "STAT 1450",
            "name": "Introduction to Statistical Reasoning",
            "term": "Autumn 2026",
            "role": "teacher",
        }
    ]
    assert client.get("/api/courses", headers=STUDENT).json()[0]["role"] == "student"


def test_course_detail(client):
    res = client.get("/api/courses/1", headers=STUDENT)
    assert res.status_code == 200
    assert res.json()["role"] == "student"


def test_unknown_course_is_404(client):
    assert client.get("/api/courses/999", headers=TEACHER).status_code == 404


def test_course_user_is_not_enrolled_in_is_403(client, db: Session):
    db.add(Course(id=2, code="OTHR 1000", name="Other", term=None))
    db.add(Enrollment(course_id=2, user_id=1, role="teacher"))
    db.commit()
    assert client.get("/api/courses/2", headers=STUDENT).status_code == 403
    assert all(c["id"] != 2 for c in client.get("/api/courses", headers=STUDENT).json())


def test_analytics_is_teacher_only(client):
    assert client.get("/api/courses/1/analytics/summary", headers=STUDENT).status_code == 403
    res = client.get("/api/courses/1/analytics/summary", headers=TEACHER)
    assert res.status_code == 200
    assert res.json() == {"course_id": 1, "status": "coming_in_phase_7"}
