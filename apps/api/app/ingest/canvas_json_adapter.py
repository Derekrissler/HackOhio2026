"""Reads Canvas REST API responses saved as JSON files (data/seed/canvas_json/courses/<id>/)."""

import json
from pathlib import Path
from typing import Any

from app.ingest import canvas_normalize as cn
from app.ingest.canonical import CourseBundle


class CanvasJsonAdapter:
    capabilities = frozenset({
        "courses", "users", "assignments", "rubrics", "quiz_questions", "quiz_responses",
        "submission_comments", "outcomes", "files", "modules",
    })

    def __init__(self, root: Path, storage_prefix: str = "") -> None:
        """`storage_prefix` turns file `url`s (relative to the seed folder) into paths relative
        to data/."""
        self.root = root
        self.storage_prefix = storage_prefix

    def course_ids(self) -> list[str]:
        return sorted(p.name for p in (self.root / "courses").iterdir() if p.is_dir())

    def _read(self, course_id: str, name: str, default: Any = None) -> Any:
        path = self.root / "courses" / course_id / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def read_course(self, course_id: str) -> CourseBundle:
        raw_modules = self._read(course_id, "modules.json", [])
        quizzes = self._read(course_id, "quizzes.json", [])
        quiz_questions = {str(q["id"]): self._read(course_id, f"quizzes/{q['id']}/questions.json", []) for q in quizzes}
        quiz_answers = {
            str(a["id"]): a.get("text", "")
            for questions in quiz_questions.values() for q in questions for a in q.get("answers", []) if "text" in a
        }

        users, enrollments = cn.normalize_users(self._read(course_id, "users.json", []), course_id)
        groups, assessments = cn.normalize_assignment_groups(
            self._read(course_id, "assignment_groups.json", []), quiz_questions, cn.module_labels(raw_modules)
        )
        files, materials = cn.normalize_course_files(
            self._read(course_id, "files.json", []), raw_modules, self.storage_prefix
        )
        submissions = []
        for raw in self._read(course_id, "submissions.json", []):
            sub, attachments = cn.normalize_submission(raw, quiz_answers, self.storage_prefix)
            submissions.append(sub)
            files.extend(attachments)

        return CourseBundle(
            course=cn.normalize_course(self._read(course_id, "course.json")),
            users=users,
            enrollments=enrollments,
            outcomes=cn.normalize_outcomes(self._read(course_id, "outcomes.json", [])),
            groups=groups,
            assessments=assessments,
            files=files,
            materials=materials,
            submissions=submissions,
            capabilities=set(self.capabilities),
        )
