"""HTTP endpoints. The host app supplies who the learner is; nothing in the request body can change that."""

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from tutor import prompts
from tutor.models import Learner
from tutor.service import NotFound, TurnRequest, TutorService

log = logging.getLogger(__name__)


class TurnBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    assessment_id: UUID | None = None
    outcome_id: UUID | None = None


def _s(value: UUID | None) -> str | None:
    return str(value) if value else None


def create_router(resolve_learner: Callable[[Request, str], Learner | None],
                  get_backend: Callable[[], tuple[TutorService, object]],
                  turns_per_minute: int = 20) -> APIRouter:
    """resolve_learner(request, course_id) identifies the student server-side.
    get_backend() returns (service, repo); it may raise RuntimeError when keys are missing."""
    router = APIRouter()
    recent: dict[str, deque] = defaultdict(deque)

    def learner_for(request: Request, course_id: str) -> Learner:
        learner = resolve_learner(request, course_id)
        if learner is None:
            raise HTTPException(404, "Not found")
        return learner

    def backend():
        try:
            return get_backend()
        except RuntimeError as e:
            raise HTTPException(503, f"Tutor is not configured: {e}")
        except Exception:
            log.exception("tutor backend unavailable")
            raise HTTPException(503, "Tutor is unavailable right now.")

    def rate_limit(learner: Learner):
        now, window = time.monotonic(), recent[learner.learner_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= turns_per_minute:
            raise HTTPException(429, "Too many messages; wait a minute.")
        window.append(now)

    @router.post("/courses/{course_id}/tutor/turn")
    def tutor_turn(course_id: str, body: TurnBody, request: Request):
        service, _ = backend()
        learner = learner_for(request, course_id)
        rate_limit(learner)
        try:
            result = service.turn(learner, TurnRequest(body.message, _s(body.session_id), _s(body.assessment_id),
                                                       _s(body.outcome_id)))
        except NotFound:
            raise HTTPException(404, "Not found")
        r = result.reply
        return {
            "session_id": result.session_id, "mode": str(result.mode), "message": r.message, "move": str(r.move),
            "hint_level": r.hint_level, "next_step": r.next_step, "fallback": result.fallback,
            "citations": [{"id": c.id, "title": c.title, "location": prompts.locator(c), "deep_link": c.deep_link}
                          for c in result.citations],
        }

    @router.get("/courses/{course_id}/tutor/sessions/{session_id}")
    def tutor_session(course_id: str, session_id: str, request: Request):
        try:
            UUID(session_id)
        except ValueError:
            raise HTTPException(404, "Not found")
        _, repo = backend()
        learner = learner_for(request, course_id)
        s = repo.get_session(session_id)
        if s is None or s.learner_id != learner.learner_id or s.course_id != learner.course_id:
            raise HTTPException(404, "Not found")
        keep = ("speaker", "content", "pedagogical_move", "hint_level", "cited_chunk_ids", "created_at")
        return {"session_id": s.id, "turns": [{k: t.get(k) for k in keep} for t in repo.session_turns(s.id)]}

    return router
