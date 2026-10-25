"""Real Supabase identity; demo cookies/pseudonyms cannot authorize tutor data."""
from collections import defaultdict, deque
import logging
import os
import time
from uuid import UUID

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from tutor.models import Learner

log = logging.getLogger(__name__)
COOKIE = "tutor_access_token"
_logins = defaultdict(deque)


def same_origin(request):
    if request.headers.get("x-tutor-request") != "1":
        raise HTTPException(403, "Same-origin tutor request required")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Same-origin tutor request required")


class LoginBody(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: SecretStr


def _sign_in_error(e: Exception) -> HTTPException:
    """Only Supabase's own 'wrong credentials' answer is the user's fault; anything else is server setup."""
    code, status = getattr(e, "code", None), getattr(e, "status", None)
    log.warning("tutor sign-in failed: %s code=%s status=%s", type(e).__name__, code, status)
    if code == "invalid_credentials":
        return HTTPException(401, "Wrong email or password")
    if code == "email_not_confirmed":
        return HTTPException(401, "This account's email isn't confirmed yet")
    if status in (401, 403) or "api key" in str(e).lower():
        return HTTPException(503, "Supabase rejected the server's key: check SUPABASE_PUBLISHABLE_KEY in "
                                  "mock-canvas/.env, then restart the server")
    return HTTPException(503, "The server couldn't reach Supabase: check SUPABASE_URL in mock-canvas/.env and "
                              "your internet connection, then restart the server")


def _rate_limit(request: Request):
    now = time.monotonic()
    attempts = _logins[request.client.host if request.client else "unknown"]
    while attempts and attempts[0] < now - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Wait before trying to sign in again")
    attempts.append(now)


def login(body: LoginBody, request: Request, response: Response):
    same_origin(request)
    _rate_limit(request)
    return _start_session(body.email, body.password.get_secret_value(), request, response)


def demo_enabled() -> bool:
    return os.environ.get("TUTOR_DEMO_AUTO_SIGNIN", "").strip().lower() in ("1", "true", "yes")


def demo_login(request: Request, response: Response):
    """Temporary demo convenience: the server signs in as the demo student (a real Supabase session, so RLS
    still applies). Off unless TUTOR_DEMO_AUTO_SIGNIN=1; the password stays server-side in DEMO_ACCOUNT_PASSWORD."""
    same_origin(request)
    if not demo_enabled():
        raise HTTPException(404, "Not found")
    password = os.environ.get("DEMO_ACCOUNT_PASSWORD", "")
    if not password:
        raise HTTPException(503, "Demo sign-in needs DEMO_ACCOUNT_PASSWORD in mock-canvas/.env")
    _rate_limit(request)
    email = os.environ.get("TUTOR_DEMO_EMAIL", "").strip() or "student1@demo.test"
    return _start_session(email, password, request, response)


def _start_session(email: str, password: str, request: Request, response: Response):
    try:
        from supabase_client import user_client
        result = user_client().auth.sign_in_with_password({"email": email, "password": password})
        token = result.session.access_token
        if not token:
            raise ValueError()
    except RuntimeError:
        raise HTTPException(503, "Tutor sign-in is not configured") from None
    except Exception as e:
        raise _sign_in_error(e) from None
    response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme == "https",
                        samesite="strict", path="/courses", max_age=min(result.session.expires_in or 3600, 3600))
    response.headers["Cache-Control"] = "no-store"
    return {"signed_in": True}


def logout(request: Request, response: Response):
    same_origin(request)
    response.delete_cookie(COOKIE, path="/courses", httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"signed_in": False}


def identity(request: Request, canvas_course_id: str):
    cached = getattr(request.state, "tutor_identity", None)
    if cached is not None:
        return cached
    header = request.headers.get("authorization")
    if header:
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer":
            token = ""
    else:
        token = request.cookies.get(COOKIE, "")
        if token and request.method not in ("GET", "HEAD"):
            same_origin(request)
    if not token:
        raise HTTPException(401, "Supabase course-account sign-in required")
    try:
        from supabase_client import user_client
        client = user_client(token)
    except (RuntimeError, ValueError):
        raise HTTPException(503, "Tutor authentication is not configured") from None
    try:
        uid = str(UUID(str(client.auth.get_user(token).user.id)))
    except Exception:
        raise HTTPException(401, "Course session is invalid or expired") from None
    try:
        courses = client.table("courses").select("id").eq("canvas_id", str(canvas_course_id)).limit(1).execute().data
        if not courses:
            raise HTTPException(403, "Not enrolled in this course")
        cid = courses[0]["id"]
        memberships = client.table("enrollments").select("role").eq("course_id", cid).eq("user_id", uid).execute().data
        if len(memberships) != 1 or memberships[0]["role"] not in ("student", "instructor", "ta"):
            raise HTTPException(403, "Not enrolled in this course")
        mappings = client.table("learner_identities").select("learner_id").eq("course_id", cid).eq("user_id", uid).execute().data
        if len(mappings) != 1:
            raise HTTPException(403, "A course learner identity is required")
        learners = client.table("learners").select("id,pseudonym").eq("course_id", cid).eq("id", mappings[0]["learner_id"]).execute().data
        if len(learners) != 1:
            raise HTTPException(403, "A course learner identity is required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Course authentication is temporarily unavailable") from None
    learner = Learner(cid, learners[0]["id"], learners[0]["pseudonym"], memberships[0]["role"])
    request.state.tutor_identity = client, learner
    return client, learner
