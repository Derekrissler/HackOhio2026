"""`python -m app.ingest.cli rebuild` — rebuild data/app.db from data/seed/ (npm run seed)."""

import argparse
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.db import DATABASE_URL, SEED_DIR, engine
from app.ingest.loader import rebuild


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["rebuild"])
    parser.add_argument("--seed-dir", type=Path, default=SEED_DIR)
    args = parser.parse_args()

    rebuild(engine, args.seed_dir)
    with Session(engine) as session:
        counts = {
            t.__tablename__: session.scalar(select(func.count()).select_from(t))
            for t in (m.User, m.Course, m.Assessment, m.Question, m.Submission, m.QuestionResponse,
                      m.Feedback, m.File, m.CourseMaterial)
        }
    print(f"Rebuilt {DATABASE_URL} from {args.seed_dir}")
    print("  " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
