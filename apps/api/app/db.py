"""SQLAlchemy engine and session setup for the SQLite database."""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
DEFAULT_DB_PATH = DATA_DIR / "app.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    """Load the seed when the database is missing, empty or from an older schema version."""
    from app.ingest.loader import SCHEMA_VERSION, rebuild

    if DATABASE_URL.startswith("sqlite:///"):
        Path(DATABASE_URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        version = conn.execute(text("PRAGMA user_version")).scalar()
    if version != SCHEMA_VERSION:
        rebuild(engine, SEED_DIR)
