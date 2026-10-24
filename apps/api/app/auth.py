"""The single authorization choke point.

Identity: demo mode trusts `X-Demo-User: <user id>`, falling back to a `demo_user` cookie (PDF
iframes cannot send headers). LTI 1.3 will later replace `current_user`; the checks below stay.

Rules for students (teachers see everything in courses they teach):
- only their own submissions, files, grades and feedback — anyone else's is a 404;
- quiz and exam questions only once they have taken it (homework prompts are always visible);
- scores, correctness, answer keys, rubric scores and comments only once graded;
- teacher-only comments never.
"""

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Assessment, Course, Enrollment, Feedback, File, Submission, User

DbSession = Annotated[Session, Depends(get_db)]


def _parse_id(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def current_user(
    db: DbSession,
    x_demo_user: Annotated[str | None, Header()] = None,
    demo_user: Annotated[str | None, Cookie()] = None,
) -> User:
    user_id = _parse_id(x_demo_user) if x_demo_user is not None else _parse_id(demo_user)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Select a demo user (X-Demo-User header)")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def enrollment_for(db: Session, course_id: int, user_id: int) -> Enrollment | None:
    return db.scalar(select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user_id))


def require_enrolled(course_id: int, user: CurrentUser, db: DbSession) -> Enrollment:
    if db.get(Course, course_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    enrollment = enrollment_for(db, course_id, user.id)
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enrolled in this course")
    return enrollment


Enrolled = Annotated[Enrollment, Depends(require_enrolled)]


def require_teacher(enrollment: Enrolled) -> Enrollment:
    if enrollment.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Instructors only")
    return enrollment


Teacher = Annotated[Enrollment, Depends(require_teacher)]


def is_teacher(enrollment: Enrollment) -> bool:
    return enrollment.role == "teacher"


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def get_assessment(db: Session, enrollment: Enrollment, assessment_id: int) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.course_id != enrollment.course_id:
        raise _not_found("Assessment")
    return assessment


def get_submission(db: Session, enrollment: Enrollment, submission_id: int) -> Submission:
    """The submission if the caller may see it; 404 otherwise (we don't confirm it exists)."""
    sub = db.get(Submission, submission_id)
    if sub is None or db.get(Assessment, sub.assessment_id).course_id != enrollment.course_id:
        raise _not_found("Submission")
    if not is_teacher(enrollment) and sub.user_id != enrollment.user_id:
        raise _not_found("Submission")
    return sub


def require_student_access(enrollment: Enrollment, user_id: int) -> None:
    """Teachers may look at any student in their course; students only at themselves."""
    if not is_teacher(enrollment) and user_id != enrollment.user_id:
        raise _not_found("User")


def require_file_access(db: Session, user: User, file_id: int) -> File:
    file = db.get(File, file_id)
    if file is None:
        raise _not_found("File")
    enrollment = enrollment_for(db, file.course_id, user.id)
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enrolled in this course")
    if file.owner_user_id is not None and not is_teacher(enrollment) and file.owner_user_id != user.id:
        raise _not_found("File")
    return file


def results_visible(enrollment: Enrollment, sub: Submission | None) -> bool:
    """Scores, correctness, answer keys, rubric scores and comments."""
    return is_teacher(enrollment) or (sub is not None and sub.workflow_state == "graded")


def questions_visible(enrollment: Enrollment, assessment: Assessment, sub: Submission | None) -> bool:
    if is_teacher(enrollment) or assessment.kind == "homework":
        return True
    return sub is not None and (sub.submitted_at is not None or sub.workflow_state == "graded")


def visible_feedback(enrollment: Enrollment, sub: Submission, rows: list[Feedback]) -> list[Feedback]:
    if is_teacher(enrollment):
        return rows
    if not results_visible(enrollment, sub):
        return []
    return [f for f in rows if f.visible_to_student]
