"""Assemble the seed: Canvas REST API-shaped JSON, manual JSON for what Canvas doesn't expose,
and PDF files. Returns {relative path: bytes} so callers can write or compare it."""

import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import count
from typing import Any

from seedgen import pdfs
from seedgen.content import COURSES, AssessmentSpec, CourseSpec
from seedgen.people import STAT_STUDENT_IDS, STUDENTS, TEACHER, Person
from seedgen.simulate import SubResult, simulate_submission

SEED = 3200

CANVAS_QUESTION_TYPES = {
    "multiple_choice": "multiple_choice_question",
    "true_false": "true_false_question",
    "numerical": "numerical_question",
}


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def dump(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class Ids:
    """Canvas-style ids from fixed ranges, allocated in a fixed order."""

    def __init__(self) -> None:
        bases = dict(group=15000, assignment=610000, quiz=32000, quiz_question=77000,
                     answer=5000, submission=880000, comment=990000, file=550000,
                     module=21000, item=22000, outcome=4100, outcome_group=4000,
                     rubric=3000, criterion=8200, enrollment=70000)
        self._counters = {k: count(v + 1) for k, v in bases.items()}

    def __call__(self, kind: str) -> int:
        return next(self._counters[kind])


def _syllabus_html(course: CourseSpec) -> str:
    objectives = "".join(
        f'<li id="{o.code}"><strong>{o.code}</strong> — {o.description}</li>' for o in course.outcomes
    )
    grading = "".join(f"<tr><td>{name}</td><td>{weight:g}%</td></tr>" for name, weight in course.groups)
    schedule = "".join(f"<li>{label}</li>" for _, label in sorted(course.weeks.items()))
    html = course.syllabus_intro + (
        f'<h2>Learning Objectives</h2><p>By the end of the course you will be able to:</p>'
        f'<ol class="learning-objectives">{objectives}</ol>'
    )
    if course.weighted:
        html += (
            "<h2>Grading</h2><table><thead><tr><th>Category</th><th>Weight</th></tr></thead>"
            f"<tbody>{grading}</tbody></table>"
        )
    return html + f"<h2>Schedule</h2><ul>{schedule}</ul>"


def build() -> dict[str, bytes]:
    rng = random.Random(SEED)
    ids = Ids()
    out: dict[str, bytes] = {}
    for course in COURSES:
        _build_course(course, rng, ids, out)
    out["README.md"] = README.encode("utf-8")
    return out


def _build_course(course: CourseSpec, rng: random.Random, ids: Ids, out: dict[str, bytes]) -> None:
    cid = course.canvas_id
    cdir = f"canvas_json/courses/{cid}"
    mdir = f"manual/{cid}"
    slug = course.code.replace(" ", "").lower()
    students = [s for s in STUDENTS if course.code != "STAT 1450" or s.id in STAT_STUDENT_IDS]
    people: list[tuple[Person, str]] = [(TEACHER, "TeacherEnrollment")] + [(s, "StudentEnrollment") for s in students]

    # -- course, users, enrollments ---------------------------------------------------------
    out[f"{cdir}/course.json"] = dump({
        "id": cid, "name": course.name, "course_code": course.code,
        "workflow_state": "available", "start_at": iso(course.start), "end_at": iso(course.end),
        "term": {"name": course.term},
        "apply_assignment_group_weights": course.weighted,
        "syllabus_body": _syllabus_html(course),
    })
    out[f"{cdir}/users.json"] = dump([
        {
            "id": p.canvas_id, "name": p.name, "sortable_name": p.sortable_name,
            "short_name": p.name, "login_id": p.email, "email": p.email,
            "enrollments": [{
                "id": ids("enrollment"), "course_id": cid, "user_id": p.canvas_id, "type": etype,
                "role": etype, "enrollment_state": "active",
            }],
        }
        for p, etype in people
    ])

    # -- outcomes ---------------------------------------------------------------------------
    group_id = ids("outcome_group")
    outcome_ids = {o.code: ids("outcome") for o in course.outcomes}
    out[f"{cdir}/outcome_groups.json"] = dump([
        {"id": group_id, "title": f"{course.code} Learning Objectives", "context_id": cid,
         "context_type": "Course", "outcomes_url": f"/api/v1/courses/{cid}/outcome_groups/{group_id}/outcomes"}
    ])
    out[f"{cdir}/outcomes.json"] = dump([
        {"id": outcome_ids[o.code], "context_id": cid, "context_type": "Course", "title": o.code,
         "display_name": o.title, "description": f"<p>{o.description}</p>",
         "points_possible": 3, "mastery_points": 2, "calculation_method": "highest"}
        for o in course.outcomes
    ])

    # -- assignment groups, assignments, quizzes ---------------------------------------------
    group_ids = {name: ids("group") for name, _ in course.groups}
    assignment_ids: dict[str, int] = {}
    quiz_ids: dict[str, int] = {}
    qq_ids: dict[tuple[str, str], int] = {}
    answer_ids: dict[tuple[str, str, str], int] = {}
    criterion_ids: dict[tuple[str, str], str] = {}
    assignments_by_group: dict[str, list[dict]] = defaultdict(list)
    quizzes_json: list[dict] = []

    for pos, spec in enumerate(course.assessments, 1):
        aid = assignment_ids[spec.key] = ids("assignment")
        assignment: dict[str, Any] = {
            "id": aid, "course_id": cid, "name": spec.title, "description": spec.description,
            "due_at": iso(spec.due), "points_possible": spec.points, "grading_type": "points",
            "assignment_group_id": group_ids[spec.group], "position": pos, "published": True,
            "submission_types": ["online_quiz"] if spec.kind == "quiz"
            else ["on_paper"] if spec.kind == "exam" else ["online_upload"],
            "is_quiz_assignment": spec.kind == "quiz",
        }
        if spec.kind == "quiz":
            qid = quiz_ids[spec.key] = ids("quiz")
            assignment["quiz_id"] = qid
            questions_json = []
            for qpos, q in enumerate(spec.questions, 1):
                qqid = qq_ids[(spec.key, q.key)] = ids("quiz_question")
                if q.qtype == "numerical":
                    answers = [{"id": ids("answer"), "numerical_answer_type": "exact_answer",
                                "exact": float(q.answer), "margin": 0, "weight": 100}]
                    answer_ids[(spec.key, q.key, q.answer)] = answers[0]["id"]
                else:
                    answers = []
                    for choice in q.choices:
                        a = {"id": ids("answer"), "text": choice, "weight": 100 if choice == q.answer else 0}
                        answer_ids[(spec.key, q.key, choice)] = a["id"]
                        answers.append(a)
                questions_json.append({
                    "id": qqid, "quiz_id": qid, "position": qpos, "question_name": f"Question {qpos}",
                    "question_type": CANVAS_QUESTION_TYPES[q.qtype], "question_text": f"<p>{q.prompt}</p>",
                    "points_possible": q.points, "answers": answers,
                    "correct_comments": "", "incorrect_comments": "",
                })
            out[f"{cdir}/quizzes/{qid}/questions.json"] = dump(questions_json)
            quizzes_json.append({
                "id": qid, "title": spec.title, "description": spec.description, "quiz_type": "assignment",
                "assignment_id": aid, "assignment_group_id": group_ids[spec.group],
                "points_possible": spec.points, "question_count": len(spec.questions),
                "due_at": iso(spec.due), "published": True, "allowed_attempts": 1, "time_limit": 20,
            })
        if spec.rubric:
            rubric_id = ids("rubric")
            criteria = []
            for crit in spec.rubric:
                crit_id = criterion_ids[(spec.key, crit.key)] = f"_{ids('criterion')}"
                points = sum(q.points for q in spec.questions if q.key in crit.question_keys)
                criteria.append({
                    "id": crit_id, "description": crit.description, "long_description": crit.long_description,
                    "points": points, "learning_outcome_id": outcome_ids[crit.outcome],
                    "ratings": [
                        {"id": f"{crit_id}_full", "description": "Full marks", "points": points},
                        {"id": f"{crit_id}_part", "description": "Partial credit", "points": points / 2},
                        {"id": f"{crit_id}_none", "description": "No marks", "points": 0},
                    ],
                })
            assignment["rubric"] = criteria
            assignment["rubric_settings"] = {"id": rubric_id, "title": f"{spec.title} Rubric",
                                             "points_possible": spec.points}
        assignments_by_group[spec.group].append(assignment)

    out[f"{cdir}/assignment_groups.json"] = dump([
        {"id": group_ids[name], "name": name, "position": pos, "group_weight": weight, "rules": {},
         "assignments": assignments_by_group[name]}
        for pos, (name, weight) in enumerate(course.groups, 1)
    ])
    out[f"{cdir}/quizzes.json"] = dump(quizzes_json)

    # Manual questions for non-quiz assessments (Canvas has no question model for them)
    manual_questions: dict[str, list[dict]] = {}
    alignments: list[dict] = []
    for spec in course.assessments:
        for q in spec.questions:
            ref = ({"quiz_question_id": qq_ids[(spec.key, q.key)]} if spec.kind == "quiz"
                   else {"assignment_id": assignment_ids[spec.key], "question_key": q.key})
            alignments += [{**ref, "outcome_id": outcome_ids[o], "weight": 1.0} for o in q.outcomes]
        if spec.kind == "quiz":
            continue
        rows: list[dict] = []
        parents_seen: list[str] = []
        for q in spec.questions:
            if q.parent and q.parent not in parents_seen:
                parents_seen.append(q.parent)
                children = [c for c in spec.questions if c.parent == q.parent]
                rows.append({"key": q.parent, "label": q.parent, "parent_key": None,
                             "prompt_html": f"<p>{spec.stems[q.parent]}</p>", "question_type": "essay",
                             "points_possible": sum(c.points for c in children), "answer_key": None,
                             "source_page": spec.pages.get(q.parent)})
            rows.append({"key": q.key, "label": q.key, "parent_key": q.parent,
                         "prompt_html": f"<p>{q.prompt}</p>", "question_type": q.qtype,
                         "points_possible": q.points, "answer_key": q.answer,
                         "source_page": spec.pages.get(q.parent or q.key)})
        for pos, row in enumerate(rows, 1):
            row["position"] = pos
        manual_questions[str(assignment_ids[spec.key])] = rows
    out[f"{mdir}/questions.json"] = dump(manual_questions)
    out[f"{mdir}/question_outcomes.json"] = dump(alignments)
    out[f"{cdir}/outcome_alignments.json"] = dump(sorted(
        ({"learning_outcome_id": outcome_ids[o], "assignment_id": assignment_ids[spec.key], "title": spec.title}
         for spec in course.assessments for o in {o for q in spec.questions for o in q.outcomes}),
        key=lambda a: (a["assignment_id"], a["learning_outcome_id"]),
    ))

    # -- materials (course files + modules) --------------------------------------------------
    files_json: list[dict] = []
    file_meta: dict[str, dict] = {}
    material_kinds: dict[str, str] = {}
    material_file_ids: dict[str, int] = {}

    def add_file(path: str, data: bytes, display: str, pages: int, text_layer: bool) -> int:
        fid = ids("file")
        out[f"files/{path}"] = data
        file_meta[str(fid)] = {"page_count": pages, "has_text_layer": text_layer,
                               "sha256": hashlib.sha256(data).hexdigest()}
        return fid

    for m in course.materials:
        data, pages = pdfs.material_pdf(course, m)
        fid = material_file_ids[m.key] = add_file(f"materials/{slug}/{m.key}.pdf", data, m.title, pages, True)
        material_kinds[str(fid)] = m.kind
        files_json.append({
            "id": fid, "display_name": f"{m.title}.pdf", "filename": f"{m.key}.pdf",
            "content-type": "application/pdf", "size": len(data),
            "url": f"files/materials/{slug}/{m.key}.pdf", "created_at": iso(course.start),
        })
    out[f"{cdir}/files.json"] = dump(files_json)

    modules = []
    for pos, (week, label) in enumerate(sorted(course.weeks.items()), 1):
        items = [{"id": ids("item"), "title": m.title, "type": "File", "content_id": material_file_ids[m.key],
                  "position": i} for i, m in enumerate((m for m in course.materials if m.week == week), 1)]
        for spec in (s for s in course.assessments if s.module == label):
            items.append({"id": ids("item"), "title": spec.title,
                          "type": "Quiz" if spec.kind == "quiz" else "Assignment",
                          "content_id": quiz_ids.get(spec.key, assignment_ids[spec.key]),
                          "position": len(items) + 1})
        modules.append({"id": ids("module"), "name": label, "position": pos, "items": items})
    out[f"{cdir}/modules.json"] = dump(modules)
    out[f"{mdir}/material_kinds.json"] = dump(material_kinds)

    # -- submissions --------------------------------------------------------------------------
    submissions_json: list[dict] = []
    responses: list[dict] = []
    q_comments: list[dict] = []
    for spec in course.assessments:
        for student in students:
            sub = simulate_submission(course, spec, student, rng)
            sid = ids("submission")
            submissions_json.append(_submission_json(course, spec, sub, sid, assignment_ids, qq_ids,
                                                     answer_ids, criterion_ids, ids, add_file, slug, rng))
            if spec.kind != "quiz":
                _manual_rows(spec, sub, sid, responses, q_comments)
    out[f"{cdir}/submissions.json"] = dump(submissions_json)
    out[f"{mdir}/question_responses.json"] = dump(responses)
    out[f"{mdir}/question_comments.json"] = dump(q_comments)
    out[f"{mdir}/file_meta.json"] = dump(file_meta)


def _submission_json(course, spec: AssessmentSpec, sub: SubResult, sid: int, assignment_ids, qq_ids,
                     answer_ids, criterion_ids, ids: Ids, add_file, slug: str, rng: random.Random) -> dict:
    data: dict[str, Any] = {
        "id": sid, "assignment_id": assignment_ids[spec.key], "user_id": sub.student.canvas_id,
        "attempt": 1 if sub.submitted_at else None,
        "submitted_at": iso(sub.submitted_at), "graded_at": iso(sub.graded_at),
        "score": sub.score, "grade": None if sub.score is None else f"{sub.score:g}",
        "workflow_state": sub.state, "late": sub.late, "missing": sub.missing, "excused": sub.excused,
        "submission_type": None, "grader_id": TEACHER.canvas_id if sub.state == "graded" else None,
    }
    if sub.submitted_at and spec.kind == "homework":
        pdf, pages = pdfs.typed_submission_pdf(course, sub)
        name = f"{spec.key}_{sub.student.id:02d}.pdf"
        fid = add_file(f"submissions/{slug}/{name}", pdf, name, pages, True)
        data["submission_type"] = "online_upload"
        data["attachments"] = [{"id": fid, "display_name": name, "filename": name,
                                "content-type": "application/pdf", "size": len(pdf),
                                "url": f"files/submissions/{slug}/{name}"}]
    elif sub.submitted_at and spec.kind == "exam":
        pdf, pages = pdfs.scanned_exam_pdf(course, sub, rng)
        name = f"{spec.key}_scan_{sub.student.id:02d}.pdf"
        fid = add_file(f"submissions/{slug}/{name}", pdf, name, pages, False)
        data["submission_type"] = "online_upload"  # scanned and uploaded by the instructor
        data["attachments"] = [{"id": fid, "display_name": name, "filename": name,
                                "content-type": "application/pdf", "size": len(pdf),
                                "url": f"files/submissions/{slug}/{name}"}]
    elif sub.submitted_at and spec.kind == "quiz":
        data["submission_type"] = "online_quiz"
        data["submission_history"] = [{
            "id": sid, "attempt": 1, "submitted_at": iso(sub.submitted_at), "score": sub.score,
            "submission_data": [
                {
                    "question_id": qq_ids[(spec.key, r.question.key)],
                    "correct": r.error is None,
                    "points": r.points,
                    "answer_id": answer_ids.get((spec.key, r.question.key, r.response)),
                    "text": r.response,
                    "more_comments": r.comment or "",
                }
                for r in sub.questions
            ],
        }]

    data["submission_comments"] = [
        {"id": ids("comment"), "author_id": TEACHER.canvas_id, "author_name": TEACHER.name,
         "comment": c.text, "created_at": iso(c.created_at), "attempt": 1,
         # Canvas returns an instructor's draft comments only to their author; we use that
         # flag for teacher-only notes.
         "draft": not c.visible}
        for c in sub.comments
    ]
    if sub.rubric:
        data["rubric_assessment"] = {
            criterion_ids[(spec.key, key)]: {"points": pts, "comments": comment or ""}
            for key, (pts, comment) in sub.rubric.items()
        }
    return data


def _manual_rows(spec: AssessmentSpec, sub: SubResult, sid: int, responses: list, comments: list) -> None:
    if not sub.submitted_at:
        return
    graded_by = "manual_entry" if spec.kind == "exam" else "instructor"
    for r in sub.questions:
        responses.append({
            "submission_id": sid, "question_key": r.question.key,
            # Scanned exams: the answer exists only as handwriting in the PDF.
            "response": None if spec.kind == "exam" else r.response,
            "points_awarded": r.points, "graded_by": graded_by,
        })
        if r.comment:
            comments.append({
                "submission_id": sid, "question_key": r.question.key, "author_id": TEACHER.canvas_id,
                "comment": r.comment, "created_at": iso(sub.graded_at + timedelta(minutes=1)),
                "visible_to_student": True,
            })


README = """# Seed data (generated — do not edit by hand)

Regenerate with `npm run seed:generate`; load into SQLite with `npm run seed`.

- `canvas_json/courses/<id>/` — data in Canvas REST API response shapes, as
  `CanvasJsonAdapter` would receive it from `/api/v1/...`. File `url`s are paths relative to
  this folder instead of download links.
- `manual/<id>/` — data Canvas does not expose: per-question scores for non-quiz work
  (including scanned exams), homework/exam question definitions, question → outcome
  alignments, material kinds and file metadata (page count, text layer).
- `files/` — lecture PDFs, typed homework uploads and image-only scanned midterms.

All people and content are fictional.
"""
