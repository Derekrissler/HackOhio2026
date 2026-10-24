"""Supabase JWT authorization, independent of mock Canvas demo identities."""

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .evidence_repository import read_pages

bearer = HTTPBearer(auto_error=False)


@dataclass
class AnalyticsSession:
    user_id: UUID
    client: Any


def analytics_session(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> AnalyticsSession:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Supabase sign-in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        from .supabase_clients import create_user_client
        client = create_user_client(credentials.credentials)
    except (RuntimeError, ImportError, ValueError):
        raise HTTPException(503, "Analytics connection is not configured") from None
    try:
        response = client.auth.get_user(credentials.credentials)
        user_id = UUID(str(response.user.id))
    except Exception:
        # Never decode unverified JWT claims or include upstream auth diagnostics.
        raise HTTPException(401, "Supabase session is invalid or expired",
                            headers={"WWW-Authenticate": "Bearer"}) from None
    return AnalyticsSession(user_id, client)


Session = Annotated[AnalyticsSession, Depends(analytics_session)]


def course_membership(session: AnalyticsSession, course_id: UUID, *, staff=False):
    rows = read_pages(session.client, "enrollments", "course_id,user_id,role",
                      filters={"course_id": str(course_id), "user_id": str(session.user_id)},
                      order=("course_id", "user_id"))
    if not rows or rows[0]["role"] not in ("student", "instructor", "ta"):
        raise HTTPException(403, "Not enrolled in this Supabase course")
    if staff and rows[0]["role"] not in ("instructor", "ta"):
        raise HTTPException(403, "Supabase course staff only")
    return rows[0]


def control_repository():
    from .repository import SupabaseAnalysisRepository
    from .supabase_clients import create_pipeline_client
    try:
        return SupabaseAnalysisRepository(create_pipeline_client())
    except (RuntimeError, ImportError, ValueError):
        raise HTTPException(503, "Analytics freshness checking is not configured") from None


def unavailable():
    # Repository exceptions contain safe internal codes, but HTTP only exposes a
    # stable message. This also covers optional analytics dependencies not installed.
    return HTTPException(503, "Analytics is temporarily unavailable")
