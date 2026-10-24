"""Response DTOs shared by the routers."""

from pydantic import BaseModel


class EnrollmentOut(BaseModel):
    course_id: int
    role: str


class MeOut(BaseModel):
    id: int
    name: str
    email: str | None
    enrollments: list[EnrollmentOut]


class DemoUserOut(BaseModel):
    id: int
    name: str
    role_summary: str


class CourseOut(BaseModel):
    id: int
    code: str
    name: str
    term: str | None
    role: str


class AnalyticsSummaryOut(BaseModel):
    course_id: int
    status: str
