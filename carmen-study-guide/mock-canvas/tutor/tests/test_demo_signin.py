"""Demo auto sign-in: a real Supabase sign-in done by the server, only when explicitly enabled."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

import supabase_client
from tutor import auth
from tutor.auth import COOKIE, demo_login

SAME_ORIGIN = {"X-Tutor-Request": "1"}


@pytest.fixture
def app(monkeypatch):
    auth._logins.clear()
    seen = []

    def fake_client(token=None):
        def sign_in(creds):
            seen.append(creds)
            return SimpleNamespace(session=SimpleNamespace(access_token="demo-jwt", expires_in=3600))
        return SimpleNamespace(auth=SimpleNamespace(sign_in_with_password=sign_in))

    monkeypatch.setattr(supabase_client, "user_client", fake_client)
    a = FastAPI()

    @a.post("/courses/{course_id}/demo")
    def demo(course_id: str, request: Request, response: Response):
        return demo_login(request, response)

    return TestClient(a), seen


def test_disabled_unless_explicitly_turned_on(app, monkeypatch):
    client, seen = app
    monkeypatch.delenv("TUTOR_DEMO_AUTO_SIGNIN", raising=False)
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORD", "pw-123456")
    assert client.post("/courses/1001/demo", headers=SAME_ORIGIN).status_code == 404
    assert seen == []


def test_enabled_signs_in_the_demo_student_and_sets_the_session_cookie(app, monkeypatch):
    client, seen = app
    monkeypatch.setenv("TUTOR_DEMO_AUTO_SIGNIN", "1")
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORD", "pw-123456")
    monkeypatch.delenv("TUTOR_DEMO_EMAIL", raising=False)
    r = client.post("/courses/1001/demo", headers=SAME_ORIGIN)
    assert r.status_code == 200 and r.cookies.get(COOKIE) == "demo-jwt"
    assert seen == [{"email": "student1@demo.test", "password": "pw-123456"}]


def test_requires_a_same_origin_request(app, monkeypatch):
    client, _ = app
    monkeypatch.setenv("TUTOR_DEMO_AUTO_SIGNIN", "1")
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORD", "pw-123456")
    assert client.post("/courses/1001/demo").status_code == 403


def test_enabled_without_a_password_is_a_setup_error(app, monkeypatch):
    client, _ = app
    monkeypatch.setenv("TUTOR_DEMO_AUTO_SIGNIN", "1")
    monkeypatch.delenv("DEMO_ACCOUNT_PASSWORD", raising=False)
    assert client.post("/courses/1001/demo", headers=SAME_ORIGIN).status_code == 503
