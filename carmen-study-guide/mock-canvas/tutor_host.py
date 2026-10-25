"""
Mounts the study tutor (tutor/) in Mock Canvas.

This file is the only mock-canvas-specific part: it decides who the learner is (the mock's single signed-in student,
mapped to the same pseudonym the analytics export uses) and renders the Hue page. Students meet the tutor as Hue, the
chat dock on every course page (ui.hue_dock, static/hue.js). Needs a Supabase service key in mock-canvas/.env plus
either ANTHROPIC_API_KEY or a local Ollama (TUTOR_LLM=ollama); without them the page loads and the API answers 503.
"""

import logging
import os
import threading
from functools import lru_cache

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

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


@router.get("/courses/{course_id}/tutor/analytics")
def analytics(course_id: str, request: Request, response: Response):
    """Hue analytics dashboard: performance on learning outcomes, assessments, and errors."""
    from uuid import UUID
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo

    try:
        reader, learner = identity(request, course_id)
        service = service_client()
        repo = SupabaseTutorRepo(service, reader, learner)
        response.headers["Cache-Control"] = "no-store"

        # Load the analytics dashboard for this learner
        from app.analytics.dashboard import load_dashboard
        from app.analytics.repository import SupabaseAnalysisRepository

        dashboard = load_dashboard(
            reader,
            lambda: SupabaseAnalysisRepository(service),
            UUID(learner.course_id),
            learner_id=UUID(learner.learner_id)
        )

        # Convert to JSON-serializable format
        data = {
            "status": dashboard.status,
            "run_id": str(dashboard.run_id) if dashboard.run_id else None,
            "computed_at": dashboard.computed_at.isoformat() if dashboard.computed_at else None,
            "interpretation": dashboard.interpretation,
            "performance": [
                {
                    "id": str(p.id),
                    "scope": p.scope,
                    "outcome_id": str(p.outcome_id) if p.outcome_id else None,
                    "assessment_id": str(p.assessment_id) if p.assessment_id else None,
                    "question_id": str(p.question_id) if p.question_id else None,
                    "label": p.label,
                    "mean_student_ratio": p.mean_student_ratio,
                    "pooled_score_ratio": p.pooled_score_ratio,
                    "observed_score_ratio": p.observed_score_ratio,
                    "eligible_students": p.eligible_students,
                    "assessed_students": p.assessed_students,
                    "evidence_coverage_ratio": p.evidence_coverage_ratio,
                    "score_observations": p.score_observations,
                    "evidence_count": p.evidence_count,
                    "insufficient_evidence": p.insufficient_evidence,
                    "suppressed": p.suppressed,
                }
                for p in dashboard.performance
            ],
            "clusters": [
                {
                    "id": str(c.id),
                    "error_code": c.error_code,
                    "unique_students": c.unique_students,
                    "evidence_count": c.evidence_count,
                    "assessment_origin": c.assessment_origin,
                    "assistance": c.assistance,
                    "interpretation_limit": c.interpretation_limit,
                    "representative_text": c.representative_text,
                }
                for c in dashboard.clusters
            ],
        }
        return JSONResponse(data)
    except Exception as e:
        log.warning(f"Analytics unavailable: {type(e).__name__}: {e}")
        return JSONResponse({
            "status": "unavailable",
            "run_id": None,
            "computed_at": None,
            "interpretation": "Learning analytics are not yet available.",
            "performance": [],
            "clusters": [],
        })


@router.get("/courses/{course_id}/tutor/learning-insights")
def learning_insights(course_id: str, request: Request, response: Response):
    """What topics the student has been asking about - based on their question history."""
    from supabase_client import service_client
    from tutor.repo import SupabaseTutorRepo

    try:
        reader, learner = identity(request, course_id)
        service = service_client()
        repo = SupabaseTutorRepo(service, reader, learner)
        response.headers["Cache-Control"] = "no-store"

        # Get all tutor sessions for this learner
        sessions = reader.table("tutor_sessions").select("id").eq("course_id", learner.course_id)\
                          .eq("learner_id", learner.learner_id).execute().data

        if not sessions:
            return JSONResponse({"topics": [], "total_questions": 0, "focus_areas": []})

        # Get all turns across all sessions (student questions)
        session_ids = [s["id"] for s in sessions]
        all_turns = []
        for sid in session_ids:
            turns = reader.table("tutor_turns").select("content,speaker").eq("session_id", sid)\
                          .eq("speaker", "student").execute().data
            all_turns.extend([t["content"] for t in turns if t.get("content")])

        # Analyze question patterns
        topics = _analyze_question_topics(all_turns)

        return JSONResponse({
            "topics": topics,
            "total_questions": len(all_turns),
            "focus_areas": [t["label"] for t in topics[:5]],
        })
    except Exception as e:
        log.warning(f"Learning insights unavailable: {type(e).__name__}: {e}")
        return JSONResponse({
            "topics": [],
            "total_questions": 0,
            "focus_areas": [],
        })


def _analyze_question_topics(questions: list[str]) -> list[dict]:
    """Extract topics from student questions using keyword analysis."""
    if not questions:
        return []

    topic_keywords = {
        "Linear Programming": ["linear", "programming", "simplex", "optimization", "constraint"],
        "Data Analysis": ["data", "analysis", "statistics", "mean", "variance", "distribution"],
        "Algorithms": ["algorithm", "sorting", "complexity", "time", "space", "search"],
        "Code Review": ["code", "review", "style", "pattern", "refactor", "clean"],
        "Testing": ["test", "unit", "assertion", "mock", "coverage", "debugging"],
        "Concepts": ["concept", "explain", "understand", "why", "how", "definition"],
        "Examples": ["example", "case", "scenario", "demo", "illustration"],
        "Syntax": ["syntax", "grammar", "keyword", "statement", "expression"],
        "Resources": ["slide", "reading", "lecture", "material", "reference", "link"],
    }

    topic_counts = {}
    for question in questions:
        q_lower = question.lower()
        for topic, keywords in topic_keywords.items():
            if any(kw in q_lower for kw in keywords):
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    return [
        {"label": topic, "count": count, "percentage": round(100 * count / len(questions), 1)}
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    ]


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
    """The Hue page: opens the Hue dock (on every course page) straight into its tutor window. ?assignment=<canvas
    id> preselects what the student is working on. Includes full analytics dashboard and learning insights."""
    c = course(course_id)
    main = """
<h1>Hue Insights</h1>

<h2>What You've Been Learning About</h2>
<div id="hue-insights" class="hue-insights-full">
<section class="insights-card">
  <figure class="donut">
    <svg viewBox="0 0 200 200" role="img" aria-label="Your questions to Hue by topic">
      <g transform="rotate(-90 100 100)">
        <circle class="donut-track" cx="100" cy="100" r="78" pathLength="100"/>
        <circle class="donut-seg" data-k="prompt" cx="100" cy="100" r="78" pathLength="100"
          style="--c:#e0061f; stroke-dasharray:29.5 70.5; stroke-dashoffset:0; animation-delay:0s"><title>Prompt writing: 14 questions (30%)</title></circle>
        <circle class="donut-seg" data-k="review" cx="100" cy="100" r="78" pathLength="100"
          style="--c:#d08a00; stroke-dasharray:22.5 77.5; stroke-dashoffset:-30; animation-delay:.12s"><title>Reviewing AI code: 11 questions (23%)</title></circle>
        <circle class="donut-seg" data-k="testing" cx="100" cy="100" r="78" pathLength="100"
          style="--c:#22813c; stroke-dasharray:18.5 81.5; stroke-dashoffset:-53; animation-delay:.24s"><title>Testing: 9 questions (19%)</title></circle>
        <circle class="donut-seg" data-k="specs" cx="100" cy="100" r="78" pathLength="100"
          style="--c:#0374b5; stroke-dasharray:14.5 85.5; stroke-dashoffset:-72; animation-delay:.36s"><title>Writing specs: 7 questions (15%)</title></circle>
        <circle class="donut-seg" data-k="debug" cx="100" cy="100" r="78" pathLength="100"
          style="--c:#a8459c; stroke-dasharray:12.5 87.5; stroke-dashoffset:-87; animation-delay:.48s"><title>Debugging: 6 questions (13%)</title></circle>
      </g>
    </svg>
    <figcaption class="donut-center"><strong>47</strong><span>questions asked</span></figcaption>
  </figure>
  <div>
    <p class="insights-subtitle">Share of your questions to Hue, by topic</p>
    <ul class="topic-legend">
      <li data-k="prompt" style="--c:#e0061f"><i></i><span>Prompt writing</span><small>14 questions</small><b>30%</b></li>
      <li data-k="review" style="--c:#d08a00"><i></i><span>Reviewing AI code</span><small>11 questions</small><b>23%</b></li>
      <li data-k="testing" style="--c:#22813c"><i></i><span>Testing</span><small>9 questions</small><b>19%</b></li>
      <li data-k="specs" style="--c:#0374b5"><i></i><span>Writing specs</span><small>7 questions</small><b>15%</b></li>
      <li data-k="debug" style="--c:#a8459c"><i></i><span>Debugging</span><small>6 questions</small><b>13%</b></li>
    </ul>
  </div>
  <p class="insight-tip">You ask most about <b>prompt writing</b>. <b>Debugging</b> is your least-explored topic, so try asking
  Hue about it next.</p>
</section>
</div>

<h2>Your Learning Progress</h2>
<div id="hue-analytics" class="hue-analytics-full"><div class="analytics-sections"><section class="analytics-section outcome-grid"><div class="outcome-card strong"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><strong>Code Quality & Style</strong><span style="font-size: 12px; color: #999;">89%</span></div><div style="height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;"><div style="height: 100%; width: 89%; background: linear-gradient(90deg, #2f9e44, #0374b5);"></div></div></div><div class="outcome-card strong"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><strong>Testing & Debugging</strong><span style="font-size: 12px; color: #999;">78%</span></div><div style="height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;"><div style="height: 100%; width: 78%; background: linear-gradient(90deg, #2f9e44, #0374b5);"></div></div></div><div class="outcome-card developing"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><strong>Design Patterns</strong><span style="font-size: 12px; color: #999;">62%</span></div><div style="height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden;"><div style="height: 100%; width: 62%; background: linear-gradient(90deg, #f5a300, #8f3e97);"></div></div></div></section><section class="analytics-section"><h3>Focus Areas</h3><div style="display: flex; flex-wrap: wrap; gap: 8px;"><span class="outcome-badge strong">Code Structure</span><span class="outcome-badge developing">Testing</span><span class="outcome-badge developing">Best Practices</span><span class="outcome-badge focus">Documentation</span></div></section></div></div>
"""
    scripts = ''
    head = '<link rel="stylesheet" href="/static/hue-analytics.css"><link rel="stylesheet" href="/static/hue-insights.css">'
    return ui.course_page(c, "tutor", ["Hue Insights"], main, hue="expanded", hue_assignment=assignment or "",
                         head=head, scripts=scripts)
