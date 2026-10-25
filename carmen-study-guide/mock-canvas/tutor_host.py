"""
Mounts the study tutor (tutor/) in Mock Canvas.

This file is the only mock-canvas-specific part: it decides who the learner is (the mock's single signed-in student,
mapped to the same pseudonym the analytics export uses) and renders the Hue page. Students meet the tutor as Hue, the
chat dock on every course page (ui.hue_dock, static/hue.js). Needs a Supabase service key in mock-canvas/.env plus
either ANTHROPIC_API_KEY or a local Ollama (TUTOR_LLM=ollama); without them the page loads and the API answers 503.
"""

import logging
import os
from functools import lru_cache

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


def backend(request):
    """Built on first use so the server starts without keys. Raises RuntimeError when not configured."""
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo

    reader, learner = identity(request, request.path_params["course_id"])
    repo = SupabaseTutorRepo(service_client(), reader, learner)
    return TutorService(repo, _llm()), repo


@lru_cache(maxsize=1)
def _llm():
    """TUTOR_LLM=anthropic|ollama. Unset: Claude when ANTHROPIC_API_KEY is set, otherwise local Ollama."""
    has_key = os.environ.get("ANTHROPIC_API_KEY", "") not in ("", "REPLACE_ME")
    provider = os.environ.get("TUTOR_LLM", "").strip().lower() or ("anthropic" if has_key else "ollama")
    if provider == "ollama":
        from tutor.llm_ollama import OllamaTutorLLM

        llm = OllamaTutorLLM()
        llm.check_ready()
        return llm
    if provider != "anthropic":
        raise RuntimeError(f"TUTOR_LLM must be 'anthropic' or 'ollama', not {provider!r}")
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
    return {"assessments": [{"id": a.id, "title": a.title, "mode": mode_for(a)} for a in repo.assessments(learner.course_id)]}


@router.get("/courses/{course_id}/tutor", response_class=HTMLResponse)
def tutor_page(course_id: str):
    """The Hue page: opens the Hue dock (on every course page) straight into its tutor window."""
    c = course(course_id)
    main = """
<h1>Hue</h1>
<p>Hue is this course's study assistant. Sign in with your Supabase course account in the window on the right, pick
what you're working on, and ask about the course material. On open, graded work Hue explains concepts and points you to
the slides, but won't give answers.</p>
<p class="muted">Hue is on every course page too: use <b>Ask Hue</b> in the corner, or the target icon on a question.</p>"""
    return ui.course_page(c, "tutor", ["Hue"], main, hue="expanded")
