"""Sign-in must only say 'wrong password' when Supabase says the credentials are wrong."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

import supabase_client
from tutor import auth
from tutor.auth import LoginBody, login


class AuthError(Exception):
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code, self.status = code, status


def client_raising(error):
    def make(token=None):
        def sign_in(_):
            raise error
        return SimpleNamespace(auth=SimpleNamespace(sign_in_with_password=sign_in))
    return make


@pytest.fixture
def post(monkeypatch):
    auth._logins.clear()
    app = FastAPI()

    @app.post("/courses/{course_id}/login")
    def sign_in(course_id: str, body: LoginBody, request: Request, response: Response):
        return login(body, request, response)

    def send(error):
        monkeypatch.setattr(supabase_client, "user_client", client_raising(error))
        return TestClient(app).post("/courses/1001/login", json={"email": "a@b.c", "password": "pw"},
                                    headers={"X-Tutor-Request": "1"})
    return send


def test_wrong_credentials_are_401(post):
    r = post(AuthError("Invalid login credentials", code="invalid_credentials", status=400))
    assert r.status_code == 401


def test_bad_api_key_is_a_server_setup_problem_not_a_wrong_password(post):
    r = post(AuthError("Invalid API key", status=401))
    assert r.status_code == 503 and "SUPABASE_PUBLISHABLE_KEY" in r.json()["detail"]


def test_unreachable_supabase_is_a_server_setup_problem(post):
    r = post(ConnectionError("getaddrinfo failed"))
    assert r.status_code == 503 and "SUPABASE_URL" in r.json()["detail"]
