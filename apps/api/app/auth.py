"""The single authorization choke point.

Demo mode trusts an `X-Demo-User: <user id>` header set by the web app's role switcher.
LTI 1.3 will later replace `current_user` with one that reads the launch token; the
`require_*` checks stay the same.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Course, Enrollment, User

DbSession = Annotated[Session, Depends(get_db)]


def current_user(db: DbSession, x_demo_user: Annotated[str | None, Header()] = None) -> User:
    user = db.get(User, int(x_demo_user)) if x_demo_user and x_demo_user.isdigit() else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Select a demo user (X-Demo-User header)")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_enrolled(course_id: int, user: CurrentUser, db: DbSession) -> Enrollment:
    if db.get(Course, course_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user.id)
    )
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enrolled in this course")
    return enrollment


def require_teacher(enrollment: Annotated[Enrollment, Depends(require_enrolled)]) -> Enrollment:
    if enrollment.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Instructors only")
    return enrollment
