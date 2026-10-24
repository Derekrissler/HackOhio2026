"""
Mounts the study tutor (tutor/) in Mock Canvas.

This file is the only mock-canvas-specific part: it decides who the learner is (the mock's single signed-in student,
mapped to the same pseudonym the analytics export uses) and renders the tutor page. Needs a Supabase service key in
mock-canvas/.env plus either ANTHROPIC_API_KEY or a local Ollama (TUTOR_LLM=ollama); without them the page loads and
the API answers 503 with what's missing.
"""

import logging
import os
from functools import lru_cache
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import ingest
import ui
from data import course, self_user
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


@lru_cache(maxsize=1)
def backend():
    """Built on first use so the server starts without keys. Raises RuntimeError when not configured."""
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo

    repo = SupabaseTutorRepo(service_client())
    return TutorService(repo, _llm()), repo


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
    """Mock Canvas has one signed-in student. Same pseudonym as ingest.py, so it matches the stored learner."""
    c = course(course_id)
    _, repo = backend()
    return repo.learner(str(c["course"]["id"]), ingest.pseudonym("S", self_user(c)["id"]))


router = create_router(current_learner, backend)


@router.get("/courses/{course_id}/tutor", response_class=HTMLResponse)
def tutor_page(course_id: str, assignment: str | None = None):
    c = course(course_id)
    try:
        _, repo = backend()
        learner = current_learner(None, course_id)
        assessments = repo.assessments(learner.course_id) if learner else []
        problem = None if learner else "This course hasn't been exported to the analytics database yet."
    except RuntimeError as e:
        assessments, problem = [], str(e)
    except Exception:
        log.exception("tutor page could not load course data")
        assessments, problem = [], "The tutor is unavailable right now. Try again in a minute."

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
