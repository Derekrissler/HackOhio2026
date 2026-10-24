import pytest

from tests.conftest import ISE_COURSE, JORDAN_ID, STAT_COURSE, STUDENT, TEACHER, as_user


def test_health_needs_no_auth(client):
    assert client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-Demo-User": "abc"}, {"X-Demo-User": "999"}])
def test_me_rejects_missing_invalid_or_unknown_user(client, headers):
    assert client.get("/api/me", headers=headers).status_code == 401


def test_me_returns_user_and_enrollments(client):
    body = client.get("/api/me", headers=STUDENT).json()
    assert body["name"] == "Alex Kim"
    assert sorted(e["course_id"] for e in body["enrollments"]) == [STAT_COURSE, ISE_COURSE]
    assert {e["role"] for e in body["enrollments"]} == {"student"}


def test_demo_users_lists_everyone_without_auth(client):
    users = client.get("/api/demo/users").json()
    assert len(users) == 21
    assert users[0]["id"] == 1 and users[0]["role_summary"] == "Teacher"
    assert {u["role_summary"] for u in users[1:]} == {"Student"}


def test_courses_lists_callers_courses_with_role(client):
    courses = client.get("/api/courses", headers=TEACHER).json()
    assert [(c["id"], c["code"], c["role"]) for c in courses] == [
        (STAT_COURSE, "STAT 1450", "teacher"),
        (ISE_COURSE, "ISE 3200", "teacher"),
    ]
    assert {c["role"] for c in client.get("/api/courses", headers=STUDENT).json()} == {"student"}


def test_course_detail(client):
    res = client.get("/api/courses/1", headers=STUDENT)
    assert res.status_code == 200
    assert res.json()["role"] == "student"


def test_unknown_course_is_404(client):
    assert client.get("/api/courses/999", headers=TEACHER).status_code == 404


def test_course_user_is_not_enrolled_in_is_403(client):
    jordan = as_user(JORDAN_ID)  # enrolled in ISE 3200 only
    assert client.get(f"/api/courses/{STAT_COURSE}", headers=jordan).status_code == 403
    assert [c["id"] for c in client.get("/api/courses", headers=jordan).json()] == [ISE_COURSE]


def test_analytics_is_teacher_only(client):
    assert client.get("/api/courses/1/analytics/summary", headers=STUDENT).status_code == 403
    res = client.get("/api/courses/1/analytics/summary", headers=TEACHER)
    assert res.status_code == 200
    assert res.json() == {"course_id": 1, "status": "coming_in_phase_7"}
