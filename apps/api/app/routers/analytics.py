"""Mock LMS entry guard plus separate JWT-authorized, read-only Supabase analytics."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.analytics.access import Session, control_repository, course_membership, unavailable
from app.analytics.dashboard import AnalyticsCourseOut, AnalyticsDashboardOut, load_dashboard
from app.analytics.evidence_repository import RepositoryError, read_pages
from app.auth import require_teacher
from app.models import Enrollment
from app.schemas import AnalyticsSummaryOut

router = APIRouter(tags=["analytics"])


@router.get("/api/courses/{course_id}/analytics/summary", response_model=AnalyticsSummaryOut)
def get_summary(enrollment: Annotated[Enrollment, Depends(require_teacher)]) -> AnalyticsSummaryOut:
    return AnalyticsSummaryOut(course_id=enrollment.course_id, status="supabase_sign_in_required")


@router.get("/api/analytics/courses", response_model=list[AnalyticsCourseOut])
def analytics_courses(session: Session, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        memberships = read_pages(session.client, "enrollments", "course_id,role", filters={"user_id": str(session.user_id)},
                                 order=("course_id", "user_id"))
        roles = {row["course_id"]: row["role"] for row in memberships}
        if not roles:
            return []
        courses = read_pages(session.client, "courses", "id,code,title,canvas_id", in_filter=("id", list(roles)))
        return [AnalyticsCourseOut(**row, role=roles[row["id"]]) for row in courses]
    except (RepositoryError, ValueError, KeyError):
        raise unavailable() from None


def dashboard_for(session, course_id, run_id, *, own=False):
    try:
        course_membership(session, course_id, staff=not own)
        learner_id = None
        if own:
            identities = read_pages(session.client, "learner_identities", "learner_id", filters={
                "course_id": str(course_id), "user_id": str(session.user_id),
            }, order=("learner_id",))
            if len(identities) != 1:
                raise HTTPException(404, "No learner identity for this Supabase course")
            learner_id = UUID(identities[0]["learner_id"])
        return load_dashboard(session.client, control_repository, course_id, learner_id=learner_id, run_id=run_id)
    except (RepositoryError, RuntimeError, ImportError, ValueError, KeyError, TypeError):
        raise unavailable() from None


@router.get("/api/analytics/courses/{course_id}/summary", response_model=AnalyticsDashboardOut)
def get_live_summary(course_id: UUID, session: Session, response: Response, run_id: UUID | None = None):
    response.headers["Cache-Control"] = "no-store"
    return dashboard_for(session, course_id, run_id)


@router.get("/api/analytics/courses/{course_id}/my-results", response_model=AnalyticsDashboardOut)
def get_my_results(course_id: UUID, session: Session, response: Response, run_id: UUID | None = None):
    response.headers["Cache-Control"] = "no-store"
    return dashboard_for(session, course_id, run_id, own=True)
