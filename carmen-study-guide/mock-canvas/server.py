"""
Mock Canvas: a local stand-in for Canvas (Carmen).

- JSON API (this file): same shapes and Link-header pagination as osu.instructure.com,
  served from the JSON files in fixtures/ (one course per file). Any bearer token works.
- HTML pages (ui.py): Canvas-styled dashboard, modules, assignments, grades, pages, files.

Run (from this folder):  .venv/bin/uvicorn server:app --reload --port 8001
"""

import re
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import ingest
import ui
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
    # Only the mock student is enrolled; teacher/TA enrollments aren't modeled.
    c = course(course_id)
    types = request.query_params.getlist("enrollment_type[]") or ["student"]
    user = self_user(c)
    users = [{"id": user["id"], "name": user["name"], "sortable_name": user["name"]}] if "student" in types else []
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
    # Instructor view: every student's submission. The mock has one student.
    c = course(course_id)
    return paginate(request, [submission_json(c, assignment(c, assignment_id), request)])


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self")
def own_submission(course_id: str, assignment_id: str, request: Request):
    c = course(course_id)
    return submission_json(c, assignment(c, assignment_id), request)


# ---------------------------------------------------------------- analytics export (ingest.py)

@app.post("/analytics/export/{course_id}")
def analytics_export(course_id: str, request: Request):
    """The 'Export for analytics' button. Runs the Canvas adapter against this server's own API."""
    course(course_id)  # 404 for an unknown course
    bundle, path = ingest.export_course(base(request), "mock", course_id)
    export_id = bundle["export"]["export_id"]
    return {"export_id": export_id, "path": str(path.relative_to(HERE)),
            "download_url": f"/analytics/exports/{export_id}/bundle.json",
            "counts": bundle["quality"]["counts"], "warnings": bundle["quality"]["warnings"]}


@app.get("/analytics/exports/{export_id}/bundle.json")
def export_download(export_id: str):
    path = ingest.EXPORTS / export_id / "bundle.json"
    if not re.fullmatch(r"EXP-[\w-]+", export_id) or not path.is_file():
        raise HTTPException(404, "export not found")
    return FileResponse(path, media_type="application/json", filename=f"{export_id}.json")


# HTML pages last, so the API routes above win on any overlap.
app.include_router(ui.router)
