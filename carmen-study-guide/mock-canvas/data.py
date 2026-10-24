"""Fixture loading shared by the JSON API (server.py) and the HTML pages (ui.py)."""

import json
from pathlib import Path

from fastapi import HTTPException

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_courses() -> dict[str, dict]:
    """Read every fixtures/**/*.json. Re-read per request so edits show up without a restart."""
    courses = {}
    for path in sorted(FIXTURES.rglob("*.json")):
        data = json.loads(path.read_text())
        data["_dir"] = path.parent
        courses[str(data["course"]["id"])] = data
    return courses


def course(course_id: str) -> dict:
    c = load_courses().get(str(course_id))
    if not c:
        raise HTTPException(404, f"No fixture for course {course_id}")
    return c


def assignment(c: dict, assignment_id: str) -> dict:
    for a in c.get("assignments", []):
        if str(a["id"]) == str(assignment_id):
            return a
    raise HTTPException(404, "assignment not found")


def submission(c: dict, assignment_id) -> dict | None:
    return c.get("submissions", {}).get(str(assignment_id))


def self_user(c: dict | None = None) -> dict:
    c = c or next(iter(load_courses().values()), {})
    return {"id": c.get("self_user_id", 1), "name": c.get("self_user_name", "Test Student")}
