"""Course home, syllabus and materials."""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth import DbSession, Enrolled, is_teacher, results_visible, visible_feedback
from app.clock import get_now
from app.models import Assessment, Course, CourseMaterial, Feedback, File, LearningOutcome, Submission
from app.schemas import (
    CourseOut,
    HomeOut,
    MaterialOut,
    ModuleOut,
    NeedsGradingOut,
    OutcomeOut,
    RecentFeedbackOut,
    SyllabusOut,
)
from app.views import assessment_summary, feedback_out, file_ref

router = APIRouter(prefix="/api/courses/{course_id}", tags=["course pages"])

UPCOMING_WINDOW = timedelta(days=14)
RECENT_FEEDBACK_LIMIT = 5


def _by_due(db: DbSession, course_id: int) -> list[Assessment]:
    return list(db.scalars(select(Assessment).where(Assessment.course_id == course_id)
                           .order_by(Assessment.due_at.is_(None), Assessment.due_at)))


@router.get("/home", response_model=HomeOut)
def get_home(enrollment: Enrolled, db: DbSession, now: Annotated[datetime, Depends(get_now)]) -> HomeOut:
    course = db.get(Course, enrollment.course_id)
    assessments = _by_due(db, course.id)
    upcoming = [a for a in assessments if a.due_at and now <= a.due_at <= now + UPCOMING_WINDOW]

    recent: list[RecentFeedbackOut] = []
    needs_grading: list[NeedsGradingOut] = []
    if is_teacher(enrollment):
        for a in assessments:
            count = len(db.scalars(select(Submission.id).where(Submission.assessment_id == a.id,
                                                               Submission.workflow_state == "submitted")).all())
            if count:
                needs_grading.append(NeedsGradingOut(assessment_id=a.id, title=a.title, count=count))
    else:
        titles = {a.id: a.title for a in assessments}
        subs = db.scalars(select(Submission).where(Submission.user_id == enrollment.user_id,
                                                   Submission.assessment_id.in_(titles))).all()
        rows: list[tuple[Feedback, Submission]] = []
        for s in subs:
            if results_visible(enrollment, s):
                rows += [(f, s) for f in visible_feedback(enrollment, s, list(s.feedback))]
        rows.sort(key=lambda fs: fs[0].created_at, reverse=True)
        for f, s in rows[:RECENT_FEEDBACK_LIMIT]:
            recent.append(RecentFeedbackOut(**feedback_out(db, f).model_dump(), submission_id=s.id,
                                            assessment_title=titles[s.assessment_id]))

    return HomeOut(
        course=CourseOut(id=course.id, code=course.code, name=course.name, term=course.term, role=enrollment.role),
        upcoming=[assessment_summary(db, enrollment, a) for a in upcoming],
        recent_feedback=recent,
        needs_grading=needs_grading,
    )


@router.get("/syllabus", response_model=SyllabusOut)
def get_syllabus(enrollment: Enrolled, db: DbSession) -> SyllabusOut:
    course = db.get(Course, enrollment.course_id)
    outcomes = db.scalars(select(LearningOutcome).where(LearningOutcome.course_id == course.id)
                          .order_by(LearningOutcome.position))
    return SyllabusOut(
        syllabus_html=course.syllabus_html,
        outcomes=[OutcomeOut(id=o.id, code=o.code, title=o.title, description=o.description) for o in outcomes],
        summary=[assessment_summary(db, enrollment, a) for a in _by_due(db, course.id)],
    )


@router.get("/materials", response_model=list[ModuleOut])
def get_materials(enrollment: Enrolled, db: DbSession) -> list[ModuleOut]:
    materials = db.scalars(select(CourseMaterial).where(CourseMaterial.course_id == enrollment.course_id)
                           .order_by(CourseMaterial.module_position, CourseMaterial.position)).all()
    modules: dict[str, ModuleOut] = {}
    for mat in materials:
        label = mat.module_label or "Other materials"
        module = modules.setdefault(label, ModuleOut(label=label, position=mat.module_position, materials=[]))
        module.materials.append(MaterialOut(id=mat.id, title=mat.title, kind=mat.kind,
                                            file=file_ref(db.get(File, mat.file_id))))
    return list(modules.values())
