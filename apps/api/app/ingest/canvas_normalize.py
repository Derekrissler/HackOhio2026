"""Canvas REST API JSON → canonical models. Pure functions, no I/O.

Shared by CanvasJsonAdapter (reads the JSON from disk) and, in Phase 4, the live API adapter.
"""

import re
from datetime import datetime
from typing import Any

from app.ingest.canonical import (
    CAssessment,
    CCourse,
    CEnrollment,
    CFeedback,
    CFile,
    CGroup,
    CMaterial,
    COutcome,
    CQuestion,
    CResponse,
    CRubricCriterion,
    CRubricScore,
    CSubmission,
    CUser,
)

Json = dict[str, Any]

QUESTION_TYPES = {
    "multiple_choice_question": "multiple_choice",
    "true_false_question": "true_false",
    "numerical_question": "numerical",
    "short_answer_question": "short_answer",
    "essay_question": "essay",
    "file_upload_question": "file",
}
ROLES = {"StudentEnrollment": "student", "TeacherEnrollment": "teacher"}


def parse_dt(value: str | None) -> datetime | None:
    """Canvas timestamps are ISO 8601 UTC ('...Z'); we store naive UTC."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None


def ext(value: Any) -> str:
    return str(value)


def normalize_course(raw: Json) -> CCourse:
    return CCourse(
        external_id=ext(raw["id"]),
        code=raw["course_code"],
        name=raw["name"],
        term=(raw.get("term") or {}).get("name"),
        syllabus_html=raw.get("syllabus_body"),
        apply_group_weights=bool(raw.get("apply_assignment_group_weights")),
        start_at=parse_dt(raw.get("start_at")),
        end_at=parse_dt(raw.get("end_at")),
    )


def normalize_users(raw_users: list[Json], course_id: Any) -> tuple[list[CUser], list[CEnrollment]]:
    users, enrollments = [], []
    for u in raw_users:
        users.append(CUser(external_id=ext(u["id"]), name=u["name"], sortable_name=u["sortable_name"],
                           email=u.get("email") or u.get("login_id")))
        for e in u.get("enrollments", []):
            role = ROLES.get(e["type"])
            if role and str(e["course_id"]) == str(course_id) and e.get("enrollment_state", "active") == "active":
                enrollments.append(CEnrollment(external_id=ext(e["id"]), user=ext(u["id"]), role=role))
    return users, enrollments


def normalize_outcomes(raw_outcomes: list[Json]) -> list[COutcome]:
    return [
        COutcome(external_id=ext(o["id"]), code=o["title"], title=o.get("display_name") or o["title"],
                 description=_strip_tags(o.get("description")), position=i)
        for i, o in enumerate(raw_outcomes, 1)
    ]


def _strip_tags(html: str | None) -> str | None:
    return re.sub(r"<[^>]+>", "", html).strip() if html else html


def _assessment_kind(assignment: Json) -> str:
    """Canvas has no 'exam' type: quizzes are flagged; exams are recognised by name."""
    if assignment.get("is_quiz_assignment") or assignment.get("quiz_id"):
        return "quiz"
    if re.search(r"\b(exam|midterm|final)\b", assignment["name"], re.I):
        return "exam"
    return "homework"


def normalize_quiz_questions(raw_questions: list[Json]) -> list[CQuestion]:
    out = []
    for q in raw_questions:
        qtype = QUESTION_TYPES.get(q["question_type"], "short_answer")
        correct = [a for a in q.get("answers", []) if a.get("weight", 0) > 0]
        if qtype == "numerical":
            key: Any = correct[0].get("exact") if correct else None
            key = f"{key:g}" if isinstance(key, float) else key
        else:
            key = correct[0].get("text") if correct else None
        out.append(CQuestion(
            external_id=ext(q["id"]), label=f"Q{q['position']}", position=q["position"],
            prompt_html=q["question_text"], question_type=qtype, points_possible=q["points_possible"],
            answer_key=key,
            choices=[a["text"] for a in q.get("answers", []) if "text" in a] or None,
        ))
    return out


def normalize_assignment_groups(
    raw_groups: list[Json],
    quiz_questions: dict[str, list[Json]],
    module_labels: dict[tuple[str, str], str],
) -> tuple[list[CGroup], list[CAssessment]]:
    """`quiz_questions` maps quiz id → raw questions; `module_labels` maps
    ('Assignment'|'Quiz', content id) → module name."""
    groups, assessments = [], []
    for g in raw_groups:
        groups.append(CGroup(external_id=ext(g["id"]), name=g["name"], weight=g.get("group_weight") or 0,
                             position=g.get("position", 0)))
        for a in g.get("assignments", []):
            quiz_id = ext(a["quiz_id"]) if a.get("quiz_id") else None
            module = module_labels.get(("Quiz", quiz_id)) if quiz_id else None
            assessments.append(CAssessment(
                external_id=ext(a["id"]),
                group=ext(g["id"]),
                title=a["name"],
                kind=_assessment_kind(a),  # type: ignore[arg-type]
                points_possible=a.get("points_possible") or 0,
                due_at=parse_dt(a.get("due_at")),
                submission_types=a.get("submission_types", []),
                description_html=a.get("description"),
                module_label=module or module_labels.get(("Assignment", ext(a["id"]))),
                position=a.get("position", 0),
                quiz_external_id=quiz_id,
                questions=normalize_quiz_questions(quiz_questions.get(quiz_id, [])) if quiz_id else [],
                rubric=[
                    CRubricCriterion(
                        external_id=c["id"], description=c["description"],
                        long_description=c.get("long_description"), points=c["points"], position=i,
                        outcome=ext(c["learning_outcome_id"]) if c.get("learning_outcome_id") else None,
                    )
                    for i, c in enumerate(a.get("rubric") or [], 1)
                ],
            ))
    return groups, assessments


def _attachment_file(att: Json, owner: str, seed_prefix: str) -> CFile:
    return CFile(
        external_id=ext(att["id"]), owner=owner, display_name=att["display_name"], filename=att["filename"],
        mime=att.get("content-type", "application/octet-stream"),
        storage_path=f"{seed_prefix}{att['url']}", size=att.get("size", 0),
    )


def normalize_submission(raw: Json, quiz_answers: dict[str, str], seed_prefix: str = "") -> tuple[CSubmission, list[CFile]]:
    """`quiz_answers` maps answer id → answer text so MC responses are stored as text."""
    user = ext(raw["user_id"])
    files = [_attachment_file(a, user, seed_prefix) for a in raw.get("attachments") or []]
    graded_at = parse_dt(raw.get("graded_at"))
    stamp = graded_at or parse_dt(raw.get("submitted_at")) or datetime(1970, 1, 1)

    responses, feedback = [], []
    history = raw.get("submission_history") or []
    for item in (history[-1].get("submission_data") or []) if history else []:
        qid = ext(item["question_id"])
        answer = quiz_answers.get(ext(item.get("answer_id"))) if item.get("answer_id") else None
        correct = item.get("correct")
        responses.append(CResponse(
            question=qid, response=answer if answer is not None else item.get("text"),
            points_awarded=item.get("points"),
            is_correct=correct if isinstance(correct, bool) else None,  # 'partial' → unknown
            graded_by="canvas_auto",
        ))
        if item.get("more_comments"):
            feedback.append(CFeedback(
                external_id=f"{raw['id']}:q{qid}", author=ext(raw.get("grader_id") or ""),
                kind="question_comment", text=item["more_comments"], created_at=stamp, question=qid,
            ))

    for c in raw.get("submission_comments") or []:
        feedback.append(CFeedback(
            external_id=ext(c["id"]), author=ext(c["author_id"]), kind="submission_comment", text=c["comment"],
            created_at=parse_dt(c["created_at"]) or stamp, attempt=c.get("attempt") or 1,
            # Draft comments are visible only to their author (the instructor).
            visible_to_student=not c.get("draft", False),
        ))

    rubric_scores = [
        CRubricScore(criterion=crit_id, points=v.get("points"), comment=v.get("comments") or None)
        for crit_id, v in (raw.get("rubric_assessment") or {}).items()
    ]
    state = raw.get("workflow_state", "unsubmitted")
    sub = CSubmission(
        external_id=ext(raw["id"]), assessment=ext(raw["assignment_id"]), user=user,
        attempt=raw.get("attempt") or 1, submitted_at=parse_dt(raw.get("submitted_at")), graded_at=graded_at,
        score=raw.get("score"), grade=raw.get("grade"), excused=bool(raw.get("excused")),
        late=bool(raw.get("late")), missing=bool(raw.get("missing")),
        workflow_state=state if state in ("unsubmitted", "submitted", "graded") else "submitted",
        file=files[0].external_id if files else None,
        responses=responses, rubric_scores=rubric_scores, feedback=feedback,
    )
    return sub, files


def normalize_course_files(raw_files: list[Json], raw_modules: list[Json], seed_prefix: str = "") -> tuple[list[CFile], list[CMaterial]]:
    files = [
        CFile(external_id=ext(f["id"]), display_name=f["display_name"], filename=f["filename"],
              mime=f.get("content-type", "application/octet-stream"),
              storage_path=f"{seed_prefix}{f['url']}", size=f.get("size", 0))
        for f in raw_files
    ]
    titles = {f.external_id: f.display_name.removesuffix(".pdf") for f in files}
    materials = [
        CMaterial(external_id=ext(item["id"]), file=ext(item["content_id"]),
                  title=item.get("title") or titles.get(ext(item["content_id"]), ""),
                  module_label=m["name"], module_position=m.get("position", 0), position=item.get("position", 0))
        for m in raw_modules
        for item in m.get("items", [])
        if item.get("type") == "File" and ext(item["content_id"]) in titles
    ]
    return files, materials


def module_labels(raw_modules: list[Json]) -> dict[tuple[str, str], str]:
    return {
        (item["type"], ext(item["content_id"])): m["name"]
        for m in raw_modules
        for item in m.get("items", [])
        if item.get("type") in ("Assignment", "Quiz")
    }
