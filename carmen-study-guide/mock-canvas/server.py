"""
Mock Canvas: a local stand-in for the slice of Canvas this project uses.

- JSON API (this file): same shapes and Link-header pagination as osu.instructure.com,
  served from the JSON files in fixtures/ (one course per file). Any bearer token works.
- HTML pages (ui.py): Canvas-styled dashboard, modules, assignments, grades. Assignment
  pages load the real extension/content.js, so you can work on the extension without Carmen.

Run (from this folder):  uvicorn server:app --reload --port 8001
Then in backend/.env:    CANVAS_BASE_URL=http://localhost:8001  and  CANVAS_TOKEN=dev
"""

from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import ui
from data import assignment, course, load_courses, submission

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


@app.get("/api/v1/courses/{course_id}/assignments")
def list_assignments(course_id: str, request: Request):
    return paginate(request, course(course_id).get("assignments", []))


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}")
def get_assignment(course_id: str, assignment_id: str):
    return assignment(course(course_id), assignment_id)


@app.get("/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self")
def own_submission(course_id: str, assignment_id: str, request: Request):
    c = course(course_id)
    a = assignment(c, assignment_id)
    sub = submission(c, assignment_id) or {"user_id": c.get("self_user_id", 1), "score": None,
                                           "workflow_state": "unsubmitted"}
    sub = {"assignment_id": a["id"], "submission_comments": [], "rubric_assessment": {}, **sub}
    includes = request.query_params.getlist("include[]")
    if "submission_comments" not in includes:
        sub.pop("submission_comments")
    if "rubric_assessment" not in includes:
        sub.pop("rubric_assessment")
    if "assignment" in includes:
        sub["assignment"] = a
    return sub


# HTML pages last, so the API routes above win on any overlap.
app.include_router(ui.router)
