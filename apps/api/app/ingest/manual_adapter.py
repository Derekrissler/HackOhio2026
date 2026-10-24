"""Adds data Canvas does not expose (data/seed/manual/<canvas course id>/) to a CourseBundle:
question definitions and per-question scores for non-quiz work (including scanned exams),
question → outcome alignments, material kinds and file metadata."""

import json
from pathlib import Path
from typing import Any

from app.ingest.canonical import CAlignment, CFeedback, CourseBundle, CQuestion, CResponse
from app.ingest.canvas_normalize import parse_dt


def manual_question_id(assignment_id: Any, key: str) -> str:
    return f"a{assignment_id}:{key}"


class ManualAdapter:
    capabilities = frozenset({
        "question_definitions", "question_scores", "scanned_exams", "question_alignments", "material_kinds",
    })

    def __init__(self, root: Path) -> None:
        self.root = root

    def _read(self, course_id: str, name: str, default: Any) -> Any:
        path = self.root / course_id / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

    def apply(self, bundle: CourseBundle) -> CourseBundle:
        cid = bundle.course.external_id
        if not (self.root / cid).is_dir():
            return bundle
        assessments = {a.external_id: a for a in bundle.assessments}
        submissions = {s.external_id: s for s in bundle.submissions}

        points: dict[str, float] = {}
        for aid, rows in self._read(cid, "questions.json", {}).items():
            assessment = assessments[aid]
            for row in rows:
                qid = manual_question_id(aid, row["key"])
                points[qid] = row["points_possible"]
                assessment.questions.append(CQuestion(
                    external_id=qid,
                    parent=manual_question_id(aid, row["parent_key"]) if row.get("parent_key") else None,
                    label=row["label"], position=row["position"], prompt_html=row["prompt_html"],
                    question_type=row["question_type"], points_possible=row["points_possible"],
                    answer_key=row.get("answer_key"), source_page=row.get("source_page"), source="manual",
                ))

        for row in self._read(cid, "question_responses.json", []):
            sub = submissions[str(row["submission_id"])]
            qid = manual_question_id(sub.assessment, row["question_key"])
            awarded = row.get("points_awarded")
            sub.responses.append(CResponse(
                question=qid, response=row.get("response"), points_awarded=awarded,
                is_correct=None if awarded is None else awarded >= points[qid],
                graded_by=row["graded_by"],
            ))

        for row in self._read(cid, "question_comments.json", []):
            sub = submissions[str(row["submission_id"])]
            qid = manual_question_id(sub.assessment, row["question_key"])
            sub.feedback.append(CFeedback(
                external_id=f"m{row['submission_id']}:{row['question_key']}", author=str(row["author_id"]),
                kind="question_comment", text=row["comment"], created_at=parse_dt(row["created_at"]),
                visible_to_student=row.get("visible_to_student", True), question=qid, source="manual",
            ))

        for row in self._read(cid, "question_outcomes.json", []):
            question = (str(row["quiz_question_id"]) if "quiz_question_id" in row
                        else manual_question_id(row["assignment_id"], row["question_key"]))
            bundle.alignments.append(CAlignment(question=question, outcome=str(row["outcome_id"]),
                                                weight=row.get("weight", 1.0), source="instructor"))

        kinds = self._read(cid, "material_kinds.json", {})
        for material in bundle.materials:
            material.kind = kinds.get(material.file, material.kind)

        meta = self._read(cid, "file_meta.json", {})
        for f in bundle.files:
            if f.external_id in meta:
                m = meta[f.external_id]
                f.page_count, f.has_text_layer, f.sha256 = m["page_count"], m["has_text_layer"], m["sha256"]

        bundle.capabilities |= self.capabilities
        return bundle
