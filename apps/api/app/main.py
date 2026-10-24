from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routers import analytics, assessments, course_pages, courses, demo, files, grades, submissions


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="HackOhio LMS API", lifespan=lifespan)
app.include_router(demo.router)
app.include_router(courses.router)
app.include_router(course_pages.router)
app.include_router(assessments.router)
app.include_router(submissions.router)
app.include_router(grades.router)
app.include_router(files.router)
app.include_router(analytics.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
