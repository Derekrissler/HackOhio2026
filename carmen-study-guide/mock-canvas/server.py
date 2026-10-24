"""
Mock Canvas: a local stand-in for Canvas (Carmen).

- JSON API (this file): same shapes and Link-header pagination as osu.instructure.com,
  served from the JSON files in fixtures/ (one course per file). Local demo tokens model staff and student access.
- HTML pages (ui.py): Canvas-styled dashboard, modules, assignments, grades, pages, files.

Run (from this folder):  .venv/bin/uvicorn server:app --reload --port 8001
"""

import re
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import db_store
import ingest
import ui
from data import assignment, course, load_courses, self_user, submission

HERE = Path(__file__).resolve().parent

app = FastAPI(title="Mock Canvas")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.middleware("http")
async def demo_api_auth(request: Request, call_next):
    """Require a declared local demo token for the Canvas-shaped JSON API."""
    match = re.match(r"^/api/v1/courses/([^/]+)(?:/|$)", request.url.path)
    if request.url.path.startswith("/api/v1/"):
        scheme, separator, token = request.headers.get("authorization", "").partition(" ")
        if not separator or scheme.lower() != "bearer" or not token.strip():
            return JSONResponse({"detail": "A Bearer token is required"}, status_code=401)
        token = token.strip()
        if match:
            try:
                c = course(match.group(1))
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        elif request.url.path.rstrip("/") == "/api/v1/courses":
            c = None
        else:
            return JSONResponse({"detail": "Unknown course scope"}, status_code=404)
        if token in {"dev", "mock"}:
            request.state.demo_role = "teacher"
            request.state.demo_user_id = None
        else:
            student_match = re.fullmatch(r"student-(\d+)", token)
            courses = [c] if c else list(load_courses().values())
            person = next((u for course_data in courses for u in course_data.get("users", [])
                           if student_match and int(student_match.group(1)) == int(u["id"])
                           and u.get("role") == "Student"), None)
            if not person or person.get("role") != "Student":
                return JSONResponse({"detail": "Use the local demo token or an enrolled student token"},
                                    status_code=401)
            request.state.demo_role = "student"
            request.state.demo_user_id = int(person["id"])
    return await call_next(request)


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
    courses = list(load_courses().values())
    if request.state.demo_role == "student":
        courses = [c for c in courses if any(u.get("id") == request.state.demo_user_id
                                             and u.get("role") == "Student" for u in c.get("users", []))]
    return paginate(request, [course_json(c, request) for c in courses])


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
    return {**a, "assignment_group_id": group_ids(c)[a.get("assignment_group", "Assignments")],
            "course_id": c["course"]["id"], "published": True}


@app.get("/api/v1/courses/{course_id}/users")
def list_users(course_id: str, request: Request):
    c = course(course_id)
    if request.state.demo_role != "teacher":
        raise HTTPException(403, "Only course staff can list all course users")
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


def quiz_responses_json(a: dict, responses: dict, graded: bool, instructor_view: bool) -> list[dict]:
    items = []
    for number, response in sorted(responses.items(), key=lambda row: int(row[0])):
        selected = response.get("selected_index")
        correct = response.get("correct_index")
        item = {
            "question_id": f"Q-{a['id']}-{int(number):02d}",
            "question_number": int(number),
            "answer_index": selected,
            "response_text": response.get("text"),
            "correct": selected == correct if graded and selected is not None and correct is not None else None,
            "points_earned": response.get("earned") if graded else None,
            "points_possible": response.get("possible"),
        }
        if instructor_view and graded and correct is not None:
            item["correct_answer_index"] = correct
        items.append(item)
    return items


def student_submission(c: dict, a: dict, user_id: int) -> dict:
    if "online_quiz" in (a.get("submission_types") or []):
        result = c.get("quiz_results", {}).get(str(a["id"]), {}).get(str(user_id))
        if result:
            return {"user_id": user_id, "attempt": 1, "workflow_state": result.get("workflow_state"),
                    "score": result.get("score"), "submitted_at": result.get("submitted_at"),
                    "graded_at": result.get("graded_at"), "responses": result.get("responses", {})}
    grade = next((item for item in c.get("student_grades", {}).get(str(user_id), [])
                  if str(item.get("assignment_id")) == str(a["id"])), None)
    if user_id == c.get("self_user_id"):
        own = submission(c, a["id"])
        if own and (own.get("score") is not None or not grade):
            return own
        if own and grade:
            return {**own, "workflow_state": "graded", "score": grade["score"],
                    "submitted_at": own.get("submitted_at") or a.get("due_at"),
                    "graded_at": grade.get("graded_at"), "late": grade.get("late", False),
                    "missing": grade.get("missing", False)}
    if grade:
        return {"user_id": user_id, "attempt": 1, "workflow_state": "graded", "score": grade["score"],
                "submitted_at": a.get("due_at"), "graded_at": grade.get("graded_at"),
                "late": grade.get("late", False), "missing": grade.get("missing", False)}
    return {"user_id": user_id, "attempt": None, "workflow_state": "unsubmitted", "score": None}


def submission_json(c: dict, a: dict, request: Request, user_id: int | None = None,
                    source: dict | None = None) -> dict:
    user_id = int(user_id if user_id is not None else request.state.demo_user_id or c.get("self_user_id", 1))
    sub = source or student_submission(c, a, user_id)
    sub = {"id": int(f"{a['id']}{sub['user_id']}"), "assignment_id": a["id"],
           "attempt": sub.get("attempt", 1 if sub.get("submitted_at") else None),
           "submission_type": (a.get("submission_types") or [None])[0], "body": None, "attachments": [],
           "submission_comments": [], "rubric_assessment": {}, **sub}
    if "online_quiz" in (a.get("submission_types") or []):
        raw_responses = sub.pop("quiz_responses", None)
        if raw_responses is None:
            raw_responses = sub.pop("responses", {})
        graded = sub.get("workflow_state") == "graded" and sub.get("score") is not None
        sub["quiz_responses"] = quiz_responses_json(
            a, raw_responses or {}, graded, instructor_view=request.state.demo_role == "teacher")
    includes = request.query_params.getlist("include[]")
    if "submission_comments" not in includes:
        sub.pop("submission_comments")
    if "rubric_assessment" not in includes:
        sub.pop("rubric_assessment")
    if "assignment" in includes:
        sub["assignment"] = assignment_json(c, a)
    return sub


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions")
def list_submissions(course_id: str, assignment_id: str, request: Request):
    c = course(course_id)
    a = assignment(c, assignment_id)
    if request.state.demo_role != "teacher":
        raise HTTPException(403, "Only course staff can list all submissions")
    people = [u for u in c.get("users", []) if u.get("role") == "Student"]
    submissions = [submission_json(c, a, request, int(person["id"])) for person in people]
    return paginate(request, submissions)


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self")
def own_submission(course_id: str, assignment_id: str, request: Request):
    c = course(course_id)
    if request.state.demo_role != "student":
        raise HTTPException(403, "Use a student demo token to read a self submission")
    return submission_json(c, assignment(c, assignment_id), request, request.state.demo_user_id)


# ---------------------------------------------------------------- analytics export (ingest.py)

@app.post("/analytics/export/{course_id}")
def analytics_export(course_id: str, request: Request):
    """The 'Export for analytics' button. Runs the Canvas adapter against this server's own API."""
    course(course_id)  # 404 for an unknown course
    bundle, path = ingest.export_course(base(request), "mock", course_id)
    export_id = bundle["export"]["export_id"]
    try:
        database = db_store.store_export(bundle, path.parent)
    except Exception as e:  # the export file is still saved; report the database error
        database = {"status": "failed", "error": str(e)[:500]}
    return {"export_id": export_id, "path": str(path.relative_to(HERE)),
            "download_url": f"/analytics/exports/{export_id}/bundle.json",
            "counts": bundle["quality"]["counts"], "warnings": bundle["quality"]["warnings"],
            "database": database}


@app.get("/analytics/exports/{export_id}/bundle.json")
def export_download(export_id: str):
    path = ingest.EXPORTS / export_id / "bundle.json"
    if not re.fullmatch(r"EXP-[\w-]+", export_id) or not path.is_file():
        raise HTTPException(404, "export not found")
    return FileResponse(path, media_type="application/json", filename=f"{export_id}.json")


# HTML pages last, so the API routes above win on any overlap.
app.include_router(ui.router)
