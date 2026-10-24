from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_enrolled
from app.models import Course, Enrollment
from app.schemas import CourseOut, EnrollmentOut, MeOut

router = APIRouter(prefix="/api", tags=["courses"])


def _course_out(course: Course, role: str) -> CourseOut:
    return CourseOut(id=course.id, code=course.code, name=course.name, term=course.term, role=role)


@router.get("/me", response_model=MeOut)
def get_me(user: CurrentUser) -> MeOut:
    return MeOut(
        id=user.id,
        name=user.name,
        email=user.email,
        enrollments=[EnrollmentOut(course_id=e.course_id, role=e.role) for e in user.enrollments],
    )


@router.get("/courses", response_model=list[CourseOut])
def list_courses(user: CurrentUser) -> list[CourseOut]:
    return [_course_out(e.course, e.role) for e in sorted(user.enrollments, key=lambda e: e.course_id)]


@router.get("/courses/{course_id}", response_model=CourseOut)
def get_course(enrollment: Annotated[Enrollment, Depends(require_enrolled)]) -> CourseOut:
    return _course_out(enrollment.course, enrollment.role)
