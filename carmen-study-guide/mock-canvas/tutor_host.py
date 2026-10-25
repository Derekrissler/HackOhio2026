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
from tutor.auth import LoginBody, identity, login, logout
from tutor.models import Learner
from tutor.policy import mode_for
from tutor.router import create_router
from tutor.service import TutorService

log = logging.getLogger(__name__)

MODE_LABELS = {
    "protected_assessment": "Protected: concept help only",
    "guided_homework": "Guided: hints, not answers",
    "independent_study": "Independent study",
}


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


@router.get("/courses/{course_id}/tutor/context")
def context(course_id: str, request: Request, response: Response):
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo
    reader, learner = identity(request, course_id)
    repo = SupabaseTutorRepo(service_client(), reader, learner)
    response.headers["Cache-Control"] = "no-store"
    # Warm the slow analytics lookup while the student reads the page, so the first message is fast.
    threading.Thread(target=repo.weak_outcomes, args=(learner.course_id, learner.learner_id), daemon=True).start()
    return {"assessments": [{"id": a.id, "title": a.title, "mode": mode_for(a)} for a in repo.assessments(learner.course_id)]}


@router.get("/courses/{course_id}/tutor", response_class=HTMLResponse)
def tutor_page(course_id: str, assignment: str | None = None):
    c = course(course_id)
    assessments, problem = [], "Sign in with your Supabase course account to use the tutor."

    options = ['<option value="">General study (no assignment)</option>'] + [
        f'<option value="{escape(a.id)}"'
        f'{" selected" if assignment and a.canvas_id == assignment else ""}>'
        f'{escape(a.title)} ({escape(MODE_LABELS[mode_for(a)])})</option>'
        for a in assessments]
    notice = f'<div class="tutor-notice" role="alert">{escape(problem)}</div>' if problem else ""
    main = f"""
<div class="content padded tutor" data-course="{escape(str(c['course']['id']))}">
  <h1>Study Tutor</h1>
  <p class="muted">Ask about the course material. On open, graded work the tutor explains concepts and points you to
  the slides, but won't give answers.</p>
  {notice}
  <form id="tutor-login-form" class="tutor-form">
    <label>Email <input name="email" type="email" autocomplete="username" required></label>
    <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
    <button type="submit">Sign in</button>
  </form>
  <button id="tutor-signout" type="button" hidden>Sign out</button>
  <label class="tutor-label" for="tutor-assessment">What are you working on?</label>
  <select id="tutor-assessment">{''.join(options)}</select>
  <div id="tutor-log" class="tutor-log" aria-live="polite"></div>
  <form id="tutor-form" class="tutor-form">
    <textarea id="tutor-input" rows="3" maxlength="4000" placeholder="Ask a question about the course…" required></textarea>
    <button class="btn btn-primary" type="submit" {"disabled" if problem else ""}>Send</button>
  </form>
</div>"""
    return ui.course_page(c, "tutor", ["Study Tutor"], main,
                          head='<link rel="stylesheet" href="/static/tutor.css">',
                          scripts='<script src="/static/tutor.js"></script>')
