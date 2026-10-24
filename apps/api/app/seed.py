"""Tiny hard-coded demo seed (1 course, 1 teacher, 3 students). All names are fictional.

Phase 3 replaces this with the Canvas-JSON seed loaded through the ingestion adapter.
"""

from sqlalchemy.orm import Session

from app.models import Course, Enrollment, User

USERS = [
    (1, "Prof. Dana Rivera", "Rivera, Dana", "drivera@example.edu"),
    (2, "Alex Kim", "Kim, Alex", "akim@example.edu"),
    (3, "Priya Natarajan", "Natarajan, Priya", "pnatarajan@example.edu"),
    (4, "Marcus Bell", "Bell, Marcus", "mbell@example.edu"),
]


def seed(session: Session) -> None:
    session.add_all(
        User(id=id_, name=name, sortable_name=sortable, email=email)
        for id_, name, sortable, email in USERS
    )
    session.add(
        Course(id=1, code="STAT 1450", name="Introduction to Statistical Reasoning", term="Autumn 2026")
    )
    session.add(Enrollment(course_id=1, user_id=1, role="teacher"))
    session.add_all(Enrollment(course_id=1, user_id=uid, role="student") for uid in (2, 3, 4))
    session.commit()
