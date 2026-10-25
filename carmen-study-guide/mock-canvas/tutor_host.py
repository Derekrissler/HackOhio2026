"""
Mounts the study tutor (tutor/) in Mock Canvas.

This file is the only mock-canvas-specific part: it decides who the learner is (the mock's single signed-in student,
mapped to the same pseudonym the analytics export uses) and renders the tutor page. Needs a Supabase service key in
mock-canvas/.env plus either ANTHROPIC_API_KEY or a local Ollama (TUTOR_LLM=ollama); without them the page loads and
the API answers 503 with what's missing.
"""

import logging
import os
import threading
from functools import lru_cache
from html import escape

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

import ui
from data import course
from tutor.auth import LoginBody, demo_enabled, demo_login, identity, login, logout
from tutor.models import Learner
from tutor.policy import mode_for
from tutor.router import create_router
from tutor.service import TutorService

log = logging.getLogger(__name__)


def backend(request):
    """Built on first use so the server starts without keys. Raises RuntimeError when not configured."""
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo

    reader, learner = identity(request, request.path_params["course_id"])
    repo = SupabaseTutorRepo(service_client(), reader, learner)
    return TutorService(repo, _llm()), repo


@lru_cache(maxsize=1)
def _llm():
    """TUTOR_LLM=anthropic|bedrock|ollama. Unset: Claude when ANTHROPIC_API_KEY is set, otherwise local Ollama."""
    has_key = os.environ.get("ANTHROPIC_API_KEY", "") not in ("", "REPLACE_ME")
    provider = os.environ.get("TUTOR_LLM", "").strip().lower() or ("anthropic" if has_key else "ollama")
    if provider == "ollama":
        from tutor.llm_ollama import OllamaTutorLLM

        llm = OllamaTutorLLM()
        llm.check_ready()
        return llm
    if provider == "bedrock":
        if not all(os.environ.get(k) for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")):
            raise RuntimeError("AWS credentials are not set in mock-canvas/.env (needed for TUTOR_LLM=bedrock)")
        # Default is Amazon Nova (AWS credits). A Claude model id switches to the Claude-on-Bedrock adapter, for
        # accounts where Anthropic model access is enabled.
        if "anthropic." in os.environ.get("BEDROCK_TUTOR_MODEL", ""):
            from tutor.llm import BedrockTutorLLM

            return BedrockTutorLLM()
        from tutor.llm_bedrock import ConverseTutorLLM

        return ConverseTutorLLM()
    if provider != "anthropic":
        raise RuntimeError(f"TUTOR_LLM must be 'anthropic', 'bedrock' or 'ollama', not {provider!r}")
    if not has_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in mock-canvas/.env (or set TUTOR_LLM=ollama)")
    from tutor.llm import AnthropicTutorLLM

    return AnthropicTutorLLM()


def current_learner(request: Request, course_id: str) -> Learner | None:
    return identity(request, course_id)[1]


router = create_router(current_learner, backend)


@router.post("/courses/{course_id}/tutor/auth/login")
def sign_in(course_id: str, body: LoginBody, request: Request, response: Response):
    return login(body, request, response)


@router.post("/courses/{course_id}/tutor/auth/logout")
def sign_out(course_id: str, request: Request, response: Response):
    return logout(request, response)


@router.post("/courses/{course_id}/tutor/auth/demo")
def demo_sign_in(course_id: str, request: Request, response: Response):
    return demo_login(request, response)


@router.get("/courses/{course_id}/tutor/context")
def context(course_id: str, request: Request, response: Response):
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo
    reader, learner = identity(request, course_id)
    repo = SupabaseTutorRepo(service_client(), reader, learner)
    response.headers["Cache-Control"] = "no-store"
    # Warm the slow analytics lookup while the student reads the page, so the first message is fast.
    threading.Thread(target=repo.weak_outcomes, args=(learner.course_id, learner.learner_id), daemon=True).start()
    return {"user": _signed_in_user(request, reader),
            "assessments": [{"id": a.id, "title": a.title, "mode": mode_for(a), "canvas_id": a.canvas_id}
                            for a in repo.assessments(learner.course_id)]}


def _signed_in_user(request: Request, reader) -> dict:
    """Name and email for the 'Signed in as' bar. Cosmetic: failures just leave it blank."""
    from tutor.auth import COOKIE
    try:
        scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
        token = bearer if scheme.lower() == "bearer" else request.cookies.get(COOKIE, "")
        user = reader.auth.get_user(token).user
        rows = reader.table("profiles").select("display_name").eq("id", user.id).limit(1).execute().data
        return {"name": rows[0]["display_name"] if rows else "", "email": user.email or ""}
    except Exception:
        return {"name": "", "email": ""}


@router.get("/courses/{course_id}/tutor", response_class=HTMLResponse)
def tutor_page(course_id: str, assignment: str | None = None):
    c = course(course_id)
    # Assessments arrive after sign-in (/tutor/context); the page only carries the preselect hint.
    main = f"""
<div class="content padded tutor" data-course="{escape(str(c['course']['id']))}"
     data-assignment="{escape(assignment or '')}" data-demo="{'1' if demo_enabled() else ''}">
  <h1>Study Tutor</h1>
  <p class="muted tutor-intro">Ask about the slides, notes and readings. On open, graded work the tutor explains the
  ideas and points you to the material, but won't give answers.</p>

  <p id="tutor-loading" class="tutor-loading" role="status">Connecting to the tutor…</p>

  <section id="tutor-signin" class="tutor-card" aria-labelledby="tutor-signin-title" hidden>
    <h2 id="tutor-signin-title">Sign in to start</h2>
    <p class="muted small">Use your course account.</p>
    <form id="tutor-login-form">
      <label class="tutor-field">Email
        <input name="email" type="email" autocomplete="username" required></label>
      <label class="tutor-field">Password
        <input name="password" type="password" autocomplete="current-password" required></label>
      <button class="btn btn-primary tutor-wide" type="submit">Sign in</button>
    </form>
    <p id="tutor-signin-error" class="tutor-alert" role="alert" hidden></p>
  </section>

  <section id="tutor-chat" hidden>
    <div class="tutor-userbar" role="status">
      <span class="tutor-avatar" aria-hidden="true"></span>
      <span class="tutor-who"></span>
      <button id="tutor-signout" class="btn tutor-signout" type="button">Sign out</button>
    </div>
    <label class="tutor-label" for="tutor-assessment">What are you working on?</label>
    <select id="tutor-assessment"></select>
    <p id="tutor-mode-banner" class="tutor-banner"></p>
    <div id="tutor-log" class="tutor-log" aria-live="polite"></div>
    <form id="tutor-form" class="tutor-compose">
      <textarea id="tutor-input" rows="2" maxlength="4000" placeholder="Ask a question about the course…"
                required></textarea>
      <button class="btn btn-primary" type="submit">Send</button>
    </form>
    <p class="muted small tutor-hint">Enter to send · Shift+Enter for a new line</p>
  </section>
</div>"""
    return ui.course_page(c, "tutor", ["Study Tutor"], main,
                          head='<link rel="stylesheet" href="/static/tutor.css">',
                          scripts='<script src="/static/tutor.js"></script>')
