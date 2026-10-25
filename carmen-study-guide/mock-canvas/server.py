"""
Mock Canvas: a local stand-in for Canvas (Carmen).

- JSON API (this file): same shapes and Link-header pagination as osu.instructure.com,
  served from the JSON files in fixtures/ (one course per file). Any bearer token works.
- HTML pages (ui.py): Canvas-styled dashboard, modules, assignments, grades, pages, files.

Run (from this folder):  .venv/bin/uvicorn server:app --reload --port 8001
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import claude_mapper
import db_store
import ingest
import sync
import ui
import uploads
from data import assignment, course, load_courses, self_user, submission

HERE = Path(__file__).resolve().parent

app = FastAPI(title="Mock Canvas")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def paginate(request: Request, items: list) -> JSONResponse:
    """Canvas-style pagination: ?page=&per_page=, next/last links in the Link header."""
    per_page = min(int(request.query_params.get("per_page", 10)), 100)
    page = int(request.query_params.get("page", 1))
    chunk = items[(page - 1) * per_page: page * per_page]
    last = max(1, -(-len(items) // per_page))

    def link(p, rel):
        params = [(k, v) for k, v in request.query_params.multi_items() if k != "page"] + [("page", p)]
        return f'<{base(request)}{request.url.path}?{urlencode(params)}>; rel="{rel}"'

    links = [link(page, "current"), link(1, "first"), link(last, "last")]
    if page < last:
        links.append(link(page + 1, "next"))
    return JSONResponse(chunk, headers={"Link": ",".join(links)})


# ---------------------------------------------------------------- PDFs

def make_pdf(pages: list[str]) -> bytes:
    """Minimal multi-page text PDF, enough for pypdf.extract_text() to read back."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def wrap(text, width=80):
        lines = []
        for para in text.splitlines():  # keep the slide's own line breaks
            line = ""
            for word in para.split():
                if line and len(line) + len(word) + 1 > width:
                    lines.append(line)
                    line = word
                else:
                    line = f"{line} {word}".strip()
            lines.append(line)
        return lines

    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        ops = "".join(f"BT /F1 12 Tf 72 {740 - 16 * i} Td ({esc(l)}) Tj ET\n" for i, l in enumerate(wrap(text)))
        stream = ops.encode("latin-1", "replace")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}endstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def pdf_bytes(c: dict, f: dict) -> bytes:
    if f.get("path"):
        return (c["_dir"] / f["path"]).read_bytes()
    return make_pdf(f.get("pages", [""]))


def file_json(request: Request, c: dict, f: dict) -> dict:
    return {
        "id": f["id"],
        "display_name": f["display_name"],
        "filename": f["display_name"],
        "content-type": f.get("content_type", "application/pdf"),
        "size": len(pdf_bytes(c, f)),
        "url": f"{base(request)}/files/{f['id']}/download",
        "locked": False,
        "hidden": False,
    }


# ---------------------------------------------------------------- API routes

def course_json(c: dict, request: Request) -> dict:
    # Like Canvas, syllabus_body only comes back with ?include[]=syllabus_body.
    out = dict(c["course"])
    if "syllabus_body" not in request.query_params.getlist("include[]"):
        out.pop("syllabus_body", None)
    return out


@app.get("/api/v1/courses")
def list_courses(request: Request):
    return paginate(request, [course_json(c, request) for c in load_courses().values()])


@app.get("/api/v1/courses/{course_id}")
def get_course(course_id: str, request: Request):
    return course_json(course(course_id), request)


@app.get("/api/v1/courses/{course_id}/modules")
def list_modules(course_id: str, request: Request):
    c, b = course(course_id), base(request)
    with_items = "items" in request.query_params.getlist("include[]")
    mods = []
    for pos, m in enumerate(c.get("modules", []), 1):
        mod = {"id": m["id"], "name": m["name"], "position": pos, "items_count": len(m.get("items", []))}
        if with_items:
            mod["items"] = [{"position": ipos, "module_id": m["id"], **it, "html_url": ui.item_url(b, course_id, it)}
                            for ipos, it in enumerate(m.get("items", []), 1)]
        mods.append(mod)
    return paginate(request, mods)


@app.get("/api/v1/courses/{course_id}/pages")
def list_pages(course_id: str, request: Request):
    # Like Canvas, the list endpoint omits the page body.
    pages = [{"url": p["url"], "title": p["title"], "published": True} for p in course(course_id).get("pages", [])]
    return paginate(request, pages)


@app.get("/api/v1/courses/{course_id}/pages/{page_url}")
def get_page(course_id: str, page_url: str, request: Request):
    for p in course(course_id).get("pages", []):
        if p["url"] == page_url:
            return {**p, "published": True, "html_url": f"{base(request)}/courses/{course_id}/pages/{page_url}"}
    raise HTTPException(404, "page not found")


@app.get("/api/v1/courses/{course_id}/files")
def list_files(course_id: str, request: Request):
    c = course(course_id)
    types = request.query_params.getlist("content_types[]")
    files = [file_json(request, c, f) for f in c.get("files", [])]
    if types:
        files = [f for f in files if f["content-type"] in types]
    return paginate(request, files)


@app.get("/files/{file_id}/download")
@app.get("/courses/{course_id}/files/{file_id}")
def download_file(file_id: int, course_id: str | None = None):
    row = uploads.get(file_id)  # a submitted file (no auth in the mock; real Canvas checks access)
    if row:
        return Response(uploads.read(row), media_type=row["content_type"],
                        headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'})
    for c in load_courses().values():
        for f in c.get("files", []):
            if f["id"] == file_id:
                return Response(pdf_bytes(c, f), media_type="application/pdf",
                                headers={"Content-Disposition": f'inline; filename="{f["display_name"]}"'})
    raise HTTPException(404, "file not found")


def group_ids(c: dict) -> dict[str, int]:
    """Canvas gives assignment groups numeric ids; the fixture names them, so number them in order."""
    names = [g["name"] for g in c.get("assignment_groups", [])]
    names += [a.get("assignment_group", "Assignments") for a in c.get("assignments", [])]
    return {n: 100 + i for i, n in enumerate(dict.fromkeys(names))}


def assignment_json(c: dict, a: dict) -> dict:
    quiz = {"quiz_id": a["id"], "is_quiz_assignment": True} if ui.is_quiz(a) else {}
    return {**a, "assignment_group_id": group_ids(c)[a.get("assignment_group", "Assignments")],
            "course_id": c["course"]["id"], "published": True, **quiz}


@app.get("/api/v1/courses/{course_id}/users")
def list_users(course_id: str, request: Request):
    c = course(course_id)
    types = request.query_params.getlist("enrollment_type[]") or ["student"]
    type_roles = {"student": "Student", "teacher": "Teacher", "ta": "Teaching Assistant"}
    users = []
    for person in c.get("users", []):
        if person.get("role", "Student") not in [type_roles.get(t, t) for t in types]:
            continue
        users.append({**person, "sortable_name": person.get("sortable_name", person["name"])})
    return paginate(request, users)


@app.get("/api/v1/courses/{course_id}/assignment_groups")
def list_assignment_groups(course_id: str, request: Request):
    c = course(course_id)
    weights = {g["name"]: g.get("group_weight") for g in c.get("assignment_groups", [])}
    return paginate(request, [{"id": gid, "name": name, "position": i + 1, "group_weight": weights.get(name, 0)}
                              for i, (name, gid) in enumerate(group_ids(c).items())])


@app.get("/api/v1/courses/{course_id}/assignments")
def list_assignments(course_id: str, request: Request):
    c = course(course_id)
    return paginate(request, [assignment_json(c, a) for a in c.get("assignments", [])])


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}")
def get_assignment(course_id: str, assignment_id: str):
    c = course(course_id)
    return assignment_json(c, assignment(c, assignment_id))


def submission_json(c: dict, a: dict, request: Request) -> dict:
    sub = submission(c, a["id"]) or {"user_id": c.get("self_user_id", 1), "score": None,
                                     "workflow_state": "unsubmitted"}
    sub = {"id": int(f"{a['id']}{sub['user_id']}"), "assignment_id": a["id"], "attempt": 1 if sub.get("submitted_at") else None,
           "submission_type": (a.get("submission_types") or [None])[0], "body": None, "attachments": [],
           "submission_comments": [], "rubric_assessment": {}, **sub}
    files = uploads.for_submission(c["course"]["id"], a["id"], sub["user_id"])
    if files:
        sub["attachments"] = [uploads.attachment_json(base(request), f) for f in files]
        sub["attempt"] = sub["attempt"] or 1
        sub["submitted_at"] = sub.get("submitted_at") or files[-1]["uploaded_at"]
    includes = request.query_params.getlist("include[]")
    if "submission_comments" not in includes:
        sub.pop("submission_comments")
    if "rubric_assessment" not in includes:
        sub.pop("rubric_assessment")
    if "assignment" in includes:
        sub["assignment"] = assignment_json(c, a)
    return sub


def quiz_submission_json(a: dict, attempt: dict, request: Request) -> dict:
    """A quiz attempt in Canvas's shape: per-question answers live in submission_history[].submission_data."""
    sub = {"id": int(f"{a['id']}{attempt['user_id']}"), "assignment_id": a["id"], "user_id": attempt["user_id"],
           "attempt": 1, "submission_type": "online_quiz", "workflow_state": attempt.get("workflow_state"),
           "score": attempt.get("score"), "submitted_at": attempt.get("submitted_at"), "graded_at": None,
           "late": False, "missing": False, "body": None, "attachments": [],
           "submission_comments": [], "rubric_assessment": {}}
    if "submission_history" in request.query_params.getlist("include[]"):
        data = []
        for qid, r in sorted(attempt.get("responses", {}).items(), key=lambda kv: int(kv[0])):
            earned, possible = r.get("earned"), r.get("possible")
            data.append({"question_id": int(qid), "answer_id": r.get("selected_index"), "text": r.get("text"),
                         "points": earned, "correct": True if earned == possible else ("partial" if earned else False),
                         "more_comments": r.get("feedback")})
        sub["submission_history"] = [{"attempt": 1, "submission_data": data}]
    return sub


def synthetic_submit_time(a: dict, g: dict) -> str | None:
    if g.get("missing") or not a.get("due_at"):
        return None
    due = datetime.fromisoformat(a["due_at"].replace("Z", "+00:00"))
    return (due + timedelta(days=1) if g.get("late") else due).isoformat()


def grade_submission_json(c: dict, a: dict, user_id: str, g: dict, request: Request) -> dict:
    """Another student's submission, built from the gradebook (no comments or rubric in the fixture)."""
    files = uploads.for_submission(c["course"]["id"], a["id"], user_id)
    return {"id": int(f"{a['id']}{user_id}"), "assignment_id": a["id"], "user_id": int(user_id),
            "attempt": 1 if files or not g.get("missing") else None,
            "submission_type": (a.get("submission_types") or [None])[0],
            "workflow_state": g.get("status"), "score": g.get("score"),
            # The gradebook fixture has no submit time; mock it as the due date (synthetic) so the
            # analytics have a real timestamp. A late submission is placed one day after the deadline.
            "submitted_at": files[-1]["uploaded_at"] if files else synthetic_submit_time(a, g),
            "graded_at": g.get("graded_at"), "late": g.get("late", False), "missing": g.get("missing", False),
            "body": None, "attachments": [uploads.attachment_json(base(request), f) for f in files],
            "submission_comments": [], "rubric_assessment": {}}


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions")
def list_submissions(course_id: str, assignment_id: str, request: Request):
    """Instructor view: every student's submission for one assignment."""
    c = course(course_id)
    a = assignment(c, assignment_id)
    if ui.is_quiz(a):
        attempts = c.get("quiz_results", {}).get(str(a["id"]), {}).values()
        return paginate(request, [quiz_submission_json(a, att, request) for att in attempts])
    subs = [submission_json(c, a, request)]  # the mock student's, with comments and rubric
    for uid, grades in c.get("student_grades", {}).items():
        g = next((g for g in grades if g["assignment_id"] == a["id"]), None)
        if g and int(uid) != subs[0]["user_id"]:
            subs.append(grade_submission_json(c, a, uid, g, request))
    return paginate(request, subs)


@app.get("/api/v1/courses/{course_id}/quizzes/{quiz_id}/questions")
def list_quiz_questions(course_id: str, quiz_id: str, request: Request):
    """Classic Quizzes question list (instructor only in Canvas): correct answers carry weight 100."""
    c = course(course_id)
    a = assignment(c, quiz_id)
    if not ui.is_quiz(a):
        raise HTTPException(404, "quiz not found")
    correct: dict[int, int] = {}
    for att in c.get("quiz_results", {}).get(str(a["id"]), {}).values():
        for qid, r in att.get("responses", {}).items():
            if r.get("correct_index") is not None:
                correct.setdefault(int(qid), r["correct_index"])
    questions = []
    for q in ui.quiz_questions(a.get("description", ""), a.get("points_possible") or 0):
        n = q["number"]
        questions.append({
            "id": n, "quiz_id": a["id"], "position": n, "question_name": f"Question {n}",
            "question_text": q["stem"], "points_possible": q["points"],
            "question_type": "multiple_choice_question" if q["options"] else "essay_question",
            "answers": [{"id": i, "text": ingest.text_of(opt), "weight": 100 if correct.get(n) == i else 0}
                        for i, opt in enumerate(q["options"])],
        })
    return paginate(request, questions)


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self")
def own_submission(course_id: str, assignment_id: str, request: Request):
    c = course(course_id)
    return submission_json(c, assignment(c, assignment_id), request)


# ---------------------------------------------------------------- analytics export (ingest.py)

def run_export(request: Request, course_id: str, assignment_id: str | None = None) -> dict:
    """Run the Canvas adapter against this server's own API, then store the bundle in Supabase."""
    bundle, path = ingest.export_course(base(request), "mock", course_id, assignment_id)
    export_id = bundle["export"]["export_id"]
    try:
        database = db_store.store_export(bundle, path.parent)
    except Exception as e:  # the export file is still saved; report the database error
        database = {"status": "failed", "error": str(e)[:500]}
    return {"export_id": export_id, "path": str(path.relative_to(HERE)), "scope": bundle["scope"],
            "download_url": f"/analytics/exports/{export_id}/bundle.json",
            "related": [{"title": d["title"], "type": d["document_type"],
                         "why": [f"{r['rule'].replace('_', ' ')}: {r['detail']}" for r in d.get("relevance", [])]}
                        for d in bundle["documents"]],
            "counts": bundle["quality"]["counts"], "warnings": bundle["quality"]["warnings"],
            "database": database}


@app.post("/analytics/export/{course_id}/assignments/{assignment_id}")
def analytics_export_assessment(course_id: str, assignment_id: str, request: Request):
    """The button on an assignment/quiz page: that assessment plus the material related to it."""
    assignment(course(course_id), assignment_id)  # 404 for an unknown course or assignment
    return run_export(request, course_id, assignment_id)


@app.post("/analytics/export/{course_id}")
def analytics_export(course_id: str, request: Request):
    """Whole-course export (no button; for scripts)."""
    course(course_id)
    return run_export(request, course_id)


# ---------------------------------------------------------------- submission uploads (uploads.py)

async def _save_upload(course_id: str, assignment_id: str, user_id: int, file: UploadFile, source: str) -> str:
    try:
        uploads.add(course_id, assignment_id, user_id, file.filename, file.content_type or "", await file.read(), source)
        return "uploaded"
    except ValueError as e:
        return f"error:{e}"


@app.post("/courses/{course_id}/assignments/{assignment_id}/submit")
async def submit_assignment(course_id: str, assignment_id: str, file: UploadFile = File(...)):
    """Student 'Submit Assignment': a PDF or image, submitted as the mock student."""
    c = course(course_id)
    assignment(c, assignment_id)
    result = await _save_upload(course_id, assignment_id, self_user(c)["id"], file, "student_submission")
    return RedirectResponse(f"/courses/{course_id}/assignments/{assignment_id}?upload={result}", status_code=303)


@app.post("/courses/{course_id}/scans")
async def upload_scan(course_id: str, user_id: int = Form(...), assignment_id: str = Form(...),
                      file: UploadFile = File(...)):
    """Instructor/TA upload of a scanned paper submission on a student's behalf."""
    c = course(course_id)
    assignment(c, assignment_id)
    if not any(u["id"] == user_id and u.get("role", "Student") == "Student" for u in c.get("users", [])):
        raise HTTPException(400, "unknown student")
    result = await _save_upload(course_id, assignment_id, user_id, file, "instructor_scan")
    return RedirectResponse(f"/courses/{course_id}/scans?upload={result}", status_code=303)


# ---------------------------------------------------------------- database sync (sync.py)

@app.post("/analytics/sync/{course_id}")
def sync_course(course_id: str, request: Request):
    """Called by every course page on load: mirror the whole course into Supabase in the background."""
    course(course_id)
    return sync.request_sync(base(request), course_id)


@app.get("/analytics/sync/{course_id}")
def sync_status(course_id: str):
    return sync.status(course_id)


# ---------------------------------------------------------------- outcome weights (claude_mapper.py)

@app.post("/analytics/outcomes/{course_id}/assignments/{assignment_id}/questions/{code:path}")
def analyze_question_goals(course_id: str, assignment_id: str, code: str):
    """The 'Analyze goals' button: Claude proposes which outcomes this question assesses, with weights."""
    c = course(course_id)
    assignment(c, assignment_id)
    try:
        return claude_mapper.map_question(c["course"]["course_code"], assignment_id, code)
    except claude_mapper.MappingError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=422)


@app.get("/analytics/exports/{export_id}/bundle.json")
def export_download(export_id: str):
    path = ingest.EXPORTS / export_id / "bundle.json"
    if not re.fullmatch(r"EXP-[\w-]+", export_id) or not path.is_file():
        raise HTTPException(404, "export not found")
    return FileResponse(path, media_type="application/json", filename=f"{export_id}.json")


# HTML pages last, so the API routes above win on any overlap.
app.include_router(ui.router)
