"""Demo-only endpoints. Removed when LTI launch replaces the role switcher."""

from fastapi import APIRouter
from sqlalchemy import select

from app.auth import DbSession
from app.models import User
from app.schemas import DemoUserOut

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/users", response_model=list[DemoUserOut])
def list_demo_users(db: DbSession) -> list[DemoUserOut]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return [
        DemoUserOut(
            id=u.id,
            name=u.name,
            role_summary="Teacher" if any(e.role == "teacher" for e in u.enrollments) else "Student",
        )
        for u in users
    ]
