import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import SEED_DIR, Base, get_db
from app.ingest.canonical import CourseBundle
from app.ingest.loader import load, read_seed
from app.main import app

# Stable ids from the seed (see apps/api/seedgen/people.py and tests/test_ingest.py)
STAT_COURSE, ISE_COURSE = 1, 2
TEACHER_ID, ALEX_ID, PRIYA_ID, MARCUS_ID, JORDAN_ID = 1, 2, 3, 4, 5


def as_user(user_id: int) -> dict[str, str]:
    return {"X-Demo-User": str(user_id)}


TEACHER = as_user(TEACHER_ID)
STUDENT = as_user(ALEX_ID)


@pytest.fixture(scope="session")
def seed_bundles() -> list[CourseBundle]:
    return read_seed(SEED_DIR)


@pytest.fixture
def db(seed_bundles) -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    for bundle in seed_bundles:
        load(bundle.model_copy(deep=True), session)
    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    # No `with` block: skips the startup hook so tests never touch data/app.db.
    yield TestClient(app)
    app.dependency_overrides.clear()
