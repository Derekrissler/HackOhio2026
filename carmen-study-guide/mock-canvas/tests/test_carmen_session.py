"""Carmen's Account > Logout signs out of Carmen and the tutor together; Log in brings both back."""

from fastapi.testclient import TestClient

import server
from carmen_session import LOGGED_OUT_COOKIE
from tutor.auth import COOKIE as TUTOR_COOKIE


def client():
    return TestClient(server.app, follow_redirects=False)


def test_account_tray_logout_is_a_real_form():
    html = client().get("/courses/1001").text
    assert 'action="/logout"' in html


def test_logout_ends_the_tutor_session_and_shows_the_logged_out_page():
    c = client()
    c.cookies.set(TUTOR_COOKIE, "some-jwt", path="/courses")
    r = c.post("/logout")
    assert r.status_code == 303 and r.headers["location"] == "/logged-out"
    set_cookies = r.headers.get_list("set-cookie")
    assert any(s.startswith(f"{LOGGED_OUT_COOKIE}=1") for s in set_cookies)
    assert any(s.startswith(f"{TUTOR_COOKIE}=") and "Max-Age=0" in s for s in set_cookies)
    page = c.get("/logged-out")
    assert page.status_code == 200 and "logged out" in page.text.lower() and 'action="/login"' in page.text


def test_while_logged_out_pages_redirect_and_the_tutor_refuses():
    c = client()
    c.cookies.set(LOGGED_OUT_COOKIE, "1")
    r = c.get("/courses/1001", headers={"accept": "text/html"})
    assert r.status_code == 303 and r.headers["location"] == "/logged-out"
    assert c.get("/courses/1001/tutor", headers={"accept": "text/html"}).status_code == 303
    assert c.post("/courses/1001/tutor/auth/demo", headers={"X-Tutor-Request": "1"}).status_code == 401
    assert c.get("/static/canvas.css").status_code == 200  # the logged-out page still needs its styles


def test_log_in_again_restores_carmen():
    c = client()
    c.cookies.set(LOGGED_OUT_COOKIE, "1")
    r = c.post("/login")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert any(s.startswith(f"{LOGGED_OUT_COOKIE}=") and "Max-Age=0" in s for s in r.headers.get_list("set-cookie"))
