"""
Carmen Study Guide backend.

- Indexes a Canvas course's material (module items, pages, PDF slides page-by-page)
  using an instructor/TA API token.
- /analyze takes a student's grader feedback and asks Claude to map each mistake to
  the concepts behind it and the specific course material to review.
  Claude may only pick material by ID from the index, so every link it returns is real.
"""

import io
import json
import os
import re
from html import unescape

import anthropic
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

load_dotenv()

CANVAS_BASE = os.environ.get("CANVAS_BASE_URL", "https://osu.instructure.com").rstrip("/")
CANVAS_TOKEN = os.environ.get("CANVAS_TOKEN", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
# "claude" (default) or "ollama" (free, runs locally: https://ollama.com)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude").lower()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
MAX_PDF_BYTES = 25 * 1024 * 1024
# Cap on material text sent to the model per request. Small local models have far smaller context windows.
MAX_CATALOG_CHARS = int(os.environ.get("MAX_CATALOG_CHARS", 300_000 if LLM_PROVIDER == "claude" else 20_000))
SNIPPET_CHARS = 1_500         # per page/slide

app = FastAPI(title="Carmen Study Guide")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
claude = anthropic.Anthropic() if LLM_PROVIDER == "claude" else None
_index: dict[str, list[dict]] = {}


# ---------------------------------------------------------------- Canvas helpers

def canvas_get_all(path: str, params: dict | None = None) -> list:
    """GET a Canvas list endpoint, following Link-header pagination."""
    if not CANVAS_TOKEN:
        raise HTTPException(500, "CANVAS_TOKEN is not set in backend/.env")
    url = f"{CANVAS_BASE}/api/v1{path}"
    params = {"per_page": 100, **(params or {})}
    headers = {"Authorization": f"Bearer {CANVAS_TOKEN}"}
    out = []
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code in (401, 403):
            raise HTTPException(r.status_code, f"Canvas denied access to {path} — check the token's course role")
        r.raise_for_status()
        data = r.json()
        out.extend(data if isinstance(data, list) else [data])
        url = r.links.get("next", {}).get("url")
        params = None  # the next URL already carries the query string
    return out


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def pdf_pages(file_obj: dict) -> list[tuple[int, str]]:
    if file_obj.get("size", 0) > MAX_PDF_BYTES:
        return []
    r = requests.get(file_obj["url"], headers={"Authorization": f"Bearer {CANVAS_TOKEN}"}, timeout=60)
    r.raise_for_status()
    reader = PdfReader(io.BytesIO(r.content))
    return [(i + 1, re.sub(r"\s+", " ", p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]


def build_index(course_id: str) -> list[dict]:
    """Return a flat list of material chunks: {id, title, url, text}."""
    items: list[dict] = []
    seen_files: set[int] = set()
    page_urls: dict[str, str] = {}

    def add(title, url, text=""):
        items.append({"id": f"m{len(items)}", "title": title, "url": url, "text": text[:SNIPPET_CHARS]})

    # Module structure (week/unit context for every item)
    for mod in canvas_get_all(f"/courses/{course_id}/modules", {"include[]": "items"}):
        for it in mod.get("items", []):
            if it.get("type") in ("SubHeader",):
                continue
            title = f"{mod['name']} › {it['title']}"
            if it.get("type") == "Page" and it.get("page_url"):
                page_urls[it["page_url"]] = title
            elif it.get("type") == "File" and it.get("content_id"):
                page_urls[f"file:{it['content_id']}"] = title
            else:
                add(title, it.get("html_url", ""))

    # Wiki pages with body text
    try:
        pages = canvas_get_all(f"/courses/{course_id}/pages")
    except Exception as e:
        print(f"[index] pages unavailable: {e}")
        pages = []
    for p in pages:
        try:
            full = canvas_get_all(f"/courses/{course_id}/pages/{p['url']}")[0]
        except Exception:
            continue
        title = page_urls.get(p["url"], p["title"])
        add(title, full.get("html_url", f"{CANVAS_BASE}/courses/{course_id}/pages/{p['url']}"),
            strip_html(full.get("body", "")))

    # PDFs (lecture slides, notes) — one chunk per page so links point at specific slides
    try:
        files = canvas_get_all(f"/courses/{course_id}/files", {"content_types[]": "application/pdf"})
    except Exception as e:
        print(f"[index] files unavailable: {e}")
        files = []
    for f in files:
        if f["id"] in seen_files:
            continue
        seen_files.add(f["id"])
        base_title = page_urls.get(f"file:{f['id']}", f["display_name"])
        file_url = f"{CANVAS_BASE}/courses/{course_id}/files/{f['id']}"
        try:
            for n, text in pdf_pages(f):
                if text:
                    add(f"{base_title} — page {n}", file_url, text)
        except Exception as e:
            print(f"[index] skipped {f['display_name']}: {e}")
            add(base_title, file_url)

    print(f"[index] course {course_id}: {len(items)} chunks")
    return items


def get_index(course_id: str) -> list[dict]:
    if course_id not in _index:
        _index[course_id] = build_index(course_id)
    return _index[course_id]


# ---------------------------------------------------------------- Claude

SYSTEM = """You are a study coach for a university course. A student will show you the grader feedback
on one of their assignments plus a catalog of the course's own materials.

Rules:
- Support learning; never give the student the answer, corrected code, or a fixed solution.
- For each distinct mistake the grader identified (comment or rubric deduction), name the underlying
  concept in a few words and explain in 1-2 sentences what the feedback suggests they misunderstood.
- Recommend 1-3 materials per mistake, chosen ONLY by their catalog id. Prefer the most specific
  item (a particular slide/page) over a whole module. If nothing fits, return an empty list.
- For each recommended material, add a short note on what to look at there.
- Skip rubric criteria that received full points and have no critical comment.
- Return ONLY JSON, no prose, in exactly this shape:
{"summary": str, "mistakes": [{"topic": str, "why": str, "resources": [{"id": str, "note": str}]}]}"""


def catalog_text(items: list[dict]) -> str:
    parts, total = [], 0
    for it in items:
        line = f"[{it['id']}] {it['title']}" + (f"\n    {it['text']}" if it["text"] else "")
        if total + len(line) > MAX_CATALOG_CHARS:
            break
        parts.append(line)
        total += len(line)
    return "\n".join(parts)


def ask_model(user: str) -> str:
    """Send SYSTEM + one user message to the configured provider and return the reply text."""
    if LLM_PROVIDER == "ollama":
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=300, json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "format": "json",
                "options": {"num_ctx": 8192, "temperature": 0.2},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            })
        except requests.ConnectionError:
            raise HTTPException(502, f"Can't reach Ollama at {OLLAMA_URL}. Is the Ollama app running?")
        if not r.ok:
            raise HTTPException(502, f"Ollama error: {r.text[:300]}")
        return r.json()["message"]["content"]

    msg = claude.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- routes

@app.get("/health")
def health():
    return {"ok": True, "canvas": CANVAS_BASE, "token_set": bool(CANVAS_TOKEN),
            "llm": f"ollama:{OLLAMA_MODEL}" if LLM_PROVIDER == "ollama" else f"claude:{MODEL}",
            "indexed_courses": {k: len(v) for k, v in _index.items()}}


@app.post("/reindex/{course_id}")
def reindex(course_id: str):
    _index.pop(course_id, None)
    items = get_index(course_id)
    return {"course_id": course_id, "chunks": len(items), "sample": [i["title"] for i in items[:20]]}


@app.post("/analyze")
def analyze(body: dict):
    course_id = str(body.get("courseId", ""))
    feedback = body.get("feedback") or {}
    if not course_id or not feedback:
        raise HTTPException(400, "courseId and feedback are required")

    items = get_index(course_id)
    by_id = {i["id"]: i for i in items}

    text = ask_model(f"<feedback>\n{json.dumps(feedback, indent=2)}\n</feedback>\n\n"
                     f"<course_materials>\n{catalog_text(items)}\n</course_materials>")
    try:
        result = parse_json(text)
    except Exception:
        raise HTTPException(502, f"Model returned non-JSON: {text[:300]}")

    # Resolve material ids to real titles/links; drop anything not in the index.
    for m in result.get("mistakes", []):
        resolved = []
        for r in m.get("resources", []):
            it = by_id.get(r.get("id"))
            if it:
                resolved.append({"title": it["title"], "url": it["url"], "note": r.get("note", "")})
        m["resources"] = resolved
    return result
