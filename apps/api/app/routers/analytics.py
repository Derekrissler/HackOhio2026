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


@router.get("/api/analytics/courses/{course_id}/clusters/{arr_id}/evidence")
def cluster_evidence(course_id: UUID, arr_id: UUID, session: Session, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        course_membership(session, course_id, staff=True)
        rows = read_pages(session.client, "analytics_results", "run_id", filters={"id": str(arr_id), "course_id": str(course_id),
                          "schema_version": "1.1", "scope": "misconception_cluster", "is_stale": False})
        if not rows:
            raise HTTPException(404, "Cluster not found")
        summary = load_dashboard(session.client, control_repository, course_id, run_id=UUID(rows[0]["run_id"]))
        if summary.status != "ready" or not any(item.id == arr_id for item in summary.clusters):
            raise HTTPException(409, "Cluster is stale or unavailable")
        from app.analytics.repository import SupabaseARRReader
        documents = SupabaseARRReader(session.client).read_published(course_id, UUID(rows[0]["run_id"]), scope="misconception_cluster")
        document = next((doc for doc in documents if doc.id == arr_id), None)
        if document is None:
            raise HTTPException(409, "Cluster is stale or unavailable")
        refs = sorted(map(str, document.metrics.group.evidence_ref_ids))
        evidence = []
        for start in range(0, len(refs), 100):
            evidence.extend(read_pages(session.client, "evidence_refs", "id,source_type,document_id,canvas_ref,page,bbox_norm,excerpt",
                                       filters={"course_id": str(course_id)}, in_filter=("id", refs[start:start+100])))
        return {"arr_id": str(arr_id), "evidence": evidence}
    except (RepositoryError, RuntimeError, ImportError, ValueError, KeyError):
        raise unavailable() from None
