"""Instructor analytics. Phase 2 only proves the teacher-only guard; Phase 7 fills it in."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import require_teacher
from app.models import Enrollment
from app.schemas import AnalyticsSummaryOut

router = APIRouter(prefix="/api/courses/{course_id}/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryOut)
def get_summary(enrollment: Annotated[Enrollment, Depends(require_teacher)]) -> AnalyticsSummaryOut:
    return AnalyticsSummaryOut(course_id=enrollment.course_id, status="coming_in_phase_7")
