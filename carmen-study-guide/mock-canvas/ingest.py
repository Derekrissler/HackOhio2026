"""
Canvas -> analytics ingestion bundle (Workstream A of the pipeline spec).

Pulls one course through the Canvas REST API and writes:

    exports/<export_id>/bundle.json           normalized source artifacts (format: INGEST_CONTRACT.md)
    exports/<export_id>/files/<doc_id>.pdf    immutable copies of the original files

The same calls work against this mock and real Canvas, so the mock and real adapters emit the same contract:

    .venv/bin/python ingest.py 1001                      # mock at http://localhost:8001
    CANVAS_BASE_URL=https://osu.instructure.com CANVAS_TOKEN=<token> .venv/bin/python ingest.py <course_id>

The bundle is evidence, not inference: identities are pseudonymous, anything Canvas doesn't return is null and
reported under "quality", and every comment, rubric note and resource chunk carries its source and a hash.
"""

import hashlib
import hmac
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
EXPORTS = HERE / "exports"
SCHEMA_VERSION = "ingest-1.0"
ADAPTER = "canvas_rest_v1"
PDF_EXTRACTOR = "pypdf-text-1"
HTML_EXTRACTOR = "html-sections-1"
MAX_FILE_BYTES = 50 * 1024 * 1024

load_dotenv(HERE / ".env")
DEV_SALT = "dev-salt"


# ---------------------------------------------------------------- Canvas client

class Canvas:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {token}"
        self.calls: list[dict] = []

    def get_all(self, path: str, params: dict | None = None, optional: bool = False) -> list | None:
        """GET a list endpoint, following Link-header pagination. optional=True returns None on 401/403/404."""
        url, params, out = f"{self.base}/api/v1{path}", {"per_page": 100, **(params or {})}, []
        while url:
            r = self.http.get(url, params=params, timeout=60)
            if optional and r.status_code in (401, 403, 404):
                self.calls.append({"path": path, "status": r.status_code})
                return None
            r.raise_for_status()
            data = json.loads(r.text.removeprefix("while(1);"))
            out.extend(data if isinstance(data, list) else [data])
            url, params = r.links.get("next", {}).get("url"), None
        self.calls.append({"path": path, "status": 200})
        return out

    def get_one(self, path: str, params: dict | None = None, optional: bool = False) -> dict | None:
        res = self.get_all(path, params, optional)
        return res[0] if res else None

    def download(self, url: str) -> bytes:
        r = self.http.get(url, timeout=120)
        r.raise_for_status()
        return r.content


# ---------------------------------------------------------------- helpers

def sha256(data: bytes | str) -> str:
    return "sha256:" + hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def pseudonym(prefix: str, raw_id) -> str:
    """Stable, non-reversible ID. Same Canvas id + same ANON_SALT -> same pseudonym across exports."""
    salt = os.environ.get("ANON_SALT", DEV_SALT).encode()
    return f"{prefix}-{hmac.new(salt, str(raw_id).encode(), hashlib.sha256).hexdigest()[:10]}"


def text_of(html: str | None) -> str:
    """HTML -> plain text, keeping line breaks between blocks."""
    if not html:
        return ""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</(p|li|tr|pre|h[1-6]|div|blockquote)>", "\n", t, flags=re.I)
    t = unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", "\n".join(line.strip() for line in t.splitlines())).strip()


def html_sections(html: str) -> list[tuple[str | None, str]]:
    """Split a page at its headings. A heading with no body of its own is folded into the next section."""
    sections, carry = [], None
    for part in re.split(r"(?=<h[1-4][^>]*>)", html or ""):
        m = re.match(r"<h([1-4])[^>]*>(.*?)</h\1>", part, flags=re.S)
        heading = text_of(m.group(2)) if m else None
        body = text_of(part[m.end():] if m else part)
        if not body:
            carry = " / ".join(x for x in (carry, heading) if x) or carry
            continue
        title = " / ".join(x for x in (carry, heading) if x) or None
        sections.append((title, f"{title}\n{body}" if title else body))
        carry = None
    return sections


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def published(obj: dict) -> str:
    if obj.get("published") is False or obj.get("hidden") or obj.get("locked"):
        return "unpublished"
    return "published"


# ---------------------------------------------------------------- exporter

class Exporter:
    def __init__(self, canvas: Canvas, course_id: str, out_dir: Path):
        self.cv, self.cid, self.out_dir = canvas, str(course_id), out_dir
        self.files_dir = out_dir / "files"
        self.evidence: list[dict] = []
        self.warnings: list[str] = []

    def evidence_ref(self, source_type: str, api_path: str, excerpt: str, **ids) -> str:
        ref_id = f"EV-{len(self.evidence) + 1:04d}"
        self.evidence.append({"id": ref_id, "source_type": source_type, "api_path": api_path,
                              "canvas_ids": ids, "excerpt": excerpt, "content_hash": sha256(excerpt)})
        return ref_id

    # ---- course + outcomes

    def course(self) -> dict:
        c = self.cv.get_one(f"/courses/{self.cid}", {"include[]": ["syllabus_body", "term"]})
        return {"course_id": self.cid, "canvas_id": c["id"], "name": c.get("name"),
                "course_code": c.get("course_code"), "term": c.get("term") if isinstance(c.get("term"), str)
                else (c.get("term") or {}).get("name"), "syllabus_html": c.get("syllabus_body")}

    def outcomes(self, syllabus_html: str | None) -> tuple[list[dict], str]:
        formal = self.cv.get_all(f"/courses/{self.cid}/outcome_group_links", {"outcome_style": "full"}, optional=True)
        if formal:
            return [{"outcome_id": f"LO-{i:02d}", "canvas_outcome_id": link["outcome"]["id"],
                     "text": link["outcome"].get("title"), "description": text_of(link["outcome"].get("description")),
                     "source": "canvas_outcomes", "source_ref": {"api_path": f"/courses/{self.cid}/outcome_group_links"},
                     "instructor_verified": True}
                    for i, link in enumerate(formal, 1)], "canvas_outcomes"

        m = re.search(r"<h[1-4][^>]*>\s*Learning (?:Objectives|Outcomes)\s*</h[1-4]>(.*?)(?=<h[1-4]|\Z)",
                      syllabus_html or "", flags=re.S | re.I)
        if not m:
            self.warnings.append("No formal Canvas outcomes and no 'Learning Objectives' section in the syllabus.")
            return [], "none"
        items = re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), flags=re.S)
        return [{"outcome_id": f"LO-{i:02d}", "canvas_outcome_id": None, "text": text_of(li), "description": None,
                 "source": "syllabus", "source_ref": {"api_path": f"/courses/{self.cid}?include[]=syllabus_body",
                                                      "section": "Learning Objectives", "item": i},
                 "instructor_verified": False}
                for i, li in enumerate(items, 1)], "syllabus_parse"

    # ---- modules (week context for documents and assessments)

    def modules(self) -> tuple[list[dict], dict]:
        mods = self.cv.get_all(f"/courses/{self.cid}/modules", {"include[]": "items"}, optional=True) or []
        where: dict = {}  # ("Page", url) / ("File", id) / ("Assignment", id) -> first module it appears in
        out = []
        for m in mods:
            items = []
            for it in m.get("items", []):
                key = {"Page": ("page", it.get("page_url")), "File": ("file", it.get("content_id")),
                       "Assignment": ("assignment", it.get("content_id"))}.get(it["type"])
                if key:
                    where.setdefault(key, {"module_id": m["id"], "module_name": m["name"], "item_title": it["title"]})
                items.append({"type": it["type"], "title": it["title"], "indent": it.get("indent", 0),
                              "ref": {"kind": key[0], "canvas_id": key[1]} if key else None,
                              "url": it.get("html_url")})
            out.append({"module_id": m["id"], "name": m["name"], "position": m.get("position"), "items": items})
        return out, where

    # ---- documents + resource chunks

    def documents(self, course: dict, where: dict) -> tuple[list[dict], list[dict]]:
        docs, chunks, seen = [], [], set()

        def add_chunk(doc, n, locator, content, method):
            h = sha256(content)
            if h in seen:  # the same text published twice (e.g. syllabus page + syllabus tab)
                return
            seen.add(h)
            link = doc["source_url"]
            if "page" in locator:
                link = f"{link}#page={locator['page']}"
            chunks.append({"chunk_id": f"CH-{doc['document_id']}-{n:03d}", "course_id": self.cid,
                           "document_id": doc["document_id"], "title": doc["title"],
                           "document_type": doc["document_type"], "locator": locator, "content": content,
                           "content_hash": h, "outcome_ids": [], "publication_status": doc["publication_status"],
                           "access_roles": doc["access_roles"], "extraction": {"method": method,
                           "version": PDF_EXTRACTOR if method == "pdf_text" else HTML_EXTRACTOR},
                           "deep_link": link})

        def add_html_doc(doc_id, title, doc_type, html, source_type, canvas_id, url, module, status):
            data = (html or "").encode()
            self.files_dir.mkdir(parents=True, exist_ok=True)
            (self.files_dir / f"{doc_id}.html").write_bytes(data)  # keep the original, like the PDFs
            doc = {"document_id": doc_id, "source_type": source_type, "canvas_id": canvas_id, "title": title,
                   "document_type": doc_type, "module": module, "content_type": "text/html",
                   "size_bytes": len(data), "sha256": sha256(data), "stored_path": f"files/{doc_id}.html",
                   "source_url": url, "page_count": None, "publication_status": status,
                   "access_roles": ["student", "instructor"]}
            docs.append(doc)
            for i, (heading, content) in enumerate(html_sections(html), 1):
                add_chunk(doc, i, {"section": heading, "section_index": i}, content, "html")

        if course["syllabus_html"]:
            add_html_doc("DOC-SYLLABUS", "Syllabus", "syllabus", course["syllabus_html"], "canvas_syllabus",
                         course["canvas_id"], f"{self.cv.base}/courses/{self.cid}/assignments/syllabus", None, "published")

        for p in self.cv.get_all(f"/courses/{self.cid}/pages", optional=True) or []:
            full = self.cv.get_one(f"/courses/{self.cid}/pages/{p['url']}", optional=True)
            if not full:
                self.warnings.append(f"Page '{p['url']}' could not be read.")
                continue
            title = full.get("title") or p["url"]
            doc_type = "syllabus" if p["url"] == "syllabus" else \
                "textbook_section" if re.search(r"textbook|chapter|glossary", title, re.I) else "course_page"
            add_html_doc(f"DOC-PAGE-{p['url']}", title, doc_type, full.get("body"), "canvas_page",
                         full.get("page_id") or p["url"], full.get("html_url"), where.get(("page", p["url"])),
                         published(full))

        files = self.cv.get_all(f"/courses/{self.cid}/files", optional=True)
        if files is None:
            self.warnings.append("Course files are not listable with this token; slides and PDFs were skipped.")
        for f in files or []:
            ctype = f.get("content-type") or f.get("content_type") or ""
            module = where.get(("file", f["id"]))
            label = f"{(module or {}).get('item_title', '')} {f['display_name']}"
            doc = {"document_id": f"DOC-{f['id']}", "source_type": "canvas_file", "canvas_id": f["id"],
                   "title": (module or {}).get("item_title") or f["display_name"], "filename": f["display_name"],
                   "document_type": "lecture_slides" if re.search(r"slide|lecture", label, re.I) else "file",
                   "module": module, "content_type": ctype, "size_bytes": f.get("size"), "sha256": None,
                   "stored_path": None, "source_url": f"{self.cv.base}/courses/{self.cid}/files/{f['id']}",
                   "page_count": None, "publication_status": published(f),
                   "access_roles": ["student", "instructor"]}
            docs.append(doc)
            if (f.get("size") or 0) > MAX_FILE_BYTES:
                self.warnings.append(f"{f['display_name']}: larger than {MAX_FILE_BYTES // 2**20} MB, not downloaded.")
                continue
            try:
                data = self.cv.download(f["url"])
            except requests.RequestException as e:
                self.warnings.append(f"{f['display_name']}: download failed ({e}).")
                continue
            self.files_dir.mkdir(parents=True, exist_ok=True)
            ext = Path(f["display_name"]).suffix or ".bin"
            (self.files_dir / f"{doc['document_id']}{ext}").write_bytes(data)
            doc.update(sha256=sha256(data), size_bytes=len(data), stored_path=f"files/{doc['document_id']}{ext}")
            if ctype == "application/pdf" or ext.lower() == ".pdf":
                try:
                    pages = PdfReader(io.BytesIO(data)).pages
                except Exception as e:
                    self.warnings.append(f"{f['display_name']}: could not parse PDF ({e}).")
                    continue
                doc["page_count"] = len(pages)
                empty = 0
                for n, page in enumerate(pages, 1):
                    text = (page.extract_text() or "").strip()
                    if text:
                        add_chunk(doc, n, {"page": n}, text, "pdf_text")
                    else:
                        empty += 1
                if empty:
                    self.warnings.append(f"{f['display_name']}: {empty} page(s) had no extractable text "
                                         f"(scanned?); they need OCR/vision in extraction.")
        return docs, chunks

    # ---- assessments + submissions

    def assessments(self, outcomes: list[dict], where: dict) -> list[dict]:
        groups = {g["id"]: g for g in self.cv.get_all(f"/courses/{self.cid}/assignment_groups", optional=True) or []}
        out = []
        for a in self.cv.get_all(f"/courses/{self.cid}/assignments") or []:
            group = groups.get(a.get("assignment_group_id"), {})
            desc_text = text_of(a.get("description"))
            out.append({
                "assessment_id": f"A-{a['id']}", "canvas_id": a["id"], "name": a["name"],
                "type": assessment_type(a, group.get("name", "")),
                "assignment_group": {"canvas_id": group.get("id"), "name": group.get("name"),
                                     "weight_percent": group.get("group_weight")} if group else None,
                "module": where.get(("assignment", a["id"])),
                "points_possible": a.get("points_possible"), "due_at": a.get("due_at"),
                "unlock_at": a.get("unlock_at"), "submission_types": a.get("submission_types"),
                "description_html": a.get("description"), "description_text": desc_text or None,
                "rubric": [{"criterion_id": r["id"], "description": r.get("description"),
                            "long_description": r.get("long_description"), "points": r.get("points"),
                            "kind": "question_part" if re.match(r"(FRQ|Part|Question|Q)\s*[\dIVX]", r.get("description") or "")
                            else "rubric_dimension"}
                           for r in a.get("rubric") or []],
                "stated_outcome_ids": stated_outcomes(desc_text, outcomes),
                "publication_status": published(a), "access_roles": ["student", "instructor"],
                "source_ref": {"api_path": f"/courses/{self.cid}/assignments/{a['id']}", "html_url": a.get("html_url")},
            })
        return out

    def students(self) -> tuple[list[dict], bool]:
        users = self.cv.get_all(f"/courses/{self.cid}/users", {"enrollment_type[]": "student"}, optional=True)
        if users is None:
            return [], False
        return [{"student_id": pseudonym("S", u["id"]), "enrollment_state": u.get("enrollment_state", "active")}
                for u in users], True

    def submissions(self, assessments: list[dict], instructor_view: bool) -> list[dict]:
        out = []
        include = {"include[]": ["submission_comments", "rubric_assessment"]}
        for a in assessments:
            path = f"/courses/{self.cid}/assignments/{a['canvas_id']}/submissions"
            subs = self.cv.get_all(path, include, optional=True) if instructor_view else None
            if subs is None:  # a student token can only read its own submission
                path += "/self"
                subs = self.cv.get_all(path, include, optional=True) or []
            criteria = {r["criterion_id"]: r for r in a["rubric"]}
            for s in subs:
                student = pseudonym("S", s["user_id"])
                rubric = []
                for crit_id, assessed in (s.get("rubric_assessment") or {}).items():
                    note = (assessed.get("comments") or "").strip()
                    rubric.append({
                        "criterion_id": crit_id, "criterion": criteria.get(crit_id, {}).get("description"),
                        "kind": criteria.get(crit_id, {}).get("kind"), "points": assessed.get("points"),
                        "points_possible": criteria.get(crit_id, {}).get("points"), "comments": note or None,
                        "evidence_ref_id": self.evidence_ref("canvas_rubric_assessment", path, note, submission_id=s.get("id"),
                                                             criterion_id=crit_id) if note else None})
                feedback = []
                for cm in s.get("submission_comments") or []:
                    text = cm.get("comment") or ""
                    feedback.append({
                        "feedback_id": f"FB-{cm.get('id')}", "kind": "submission_comment",
                        "author_role": "student" if cm.get("author_id") == s["user_id"] else "grader",
                        "author_id": pseudonym("S" if cm.get("author_id") == s["user_id"] else "G", cm.get("author_id")),
                        "text": text, "created_at": cm.get("created_at"),
                        "evidence_ref_id": self.evidence_ref("canvas_submission_comment", path, text,
                                                             submission_id=s.get("id"), comment_id=cm.get("id"))})
                body = text_of(s.get("body"))
                out.append({
                    "submission_id": f"SUB-{a['canvas_id']}-{student}", "canvas_id": s.get("id"),
                    "assessment_id": a["assessment_id"], "student_id": student,
                    "attempt_id": str(s["attempt"]) if s.get("attempt") is not None else None,
                    "workflow_state": s.get("workflow_state"), "late": s.get("late"), "missing": s.get("missing"),
                    "submitted_at": s.get("submitted_at"), "graded_at": s.get("graded_at"),
                    "score": s.get("score"), "points_possible": a["points_possible"],
                    "response": {"submission_type": s.get("submission_type"), "body_text": body or None,
                                 "attachments": [{"canvas_file_id": att.get("id"), "filename": att.get("filename"),
                                                  "content_type": att.get("content-type"), "url": att.get("url"),
                                                  "access_roles": ["instructor", "owner"]}
                                                 for att in s.get("attachments") or []]},
                    "rubric_assessment": rubric, "feedback": feedback,
                    "source_ref": {"api_path": path},
                })
        return out

    # ---- bundle

    def run(self) -> dict:
        course = self.course()
        outcomes, outcome_source = self.outcomes(course["syllabus_html"])
        modules, where = self.modules()
        documents, chunks = self.documents(course, where)
        assessments = self.assessments(outcomes, where)
        students, instructor_view = self.students()
        submissions = self.submissions(assessments, instructor_view)
        if not students:
            students = [{"student_id": sid, "enrollment_state": None}
                        for sid in dict.fromkeys(s["student_id"] for s in submissions)]

        if os.environ.get("ANON_SALT", DEV_SALT) == DEV_SALT:
            self.warnings.append("ANON_SALT is not set; pseudonyms use the development salt.")
        if submissions and not any(s["response"]["body_text"] or s["response"]["attachments"] for s in submissions):
            self.warnings.append("No submission bodies or attachments: student responses are not available, so "
                                 "evidence is assignment- and rubric-level (no question-level response text).")
        if not instructor_view:
            self.warnings.append("Token can't list course enrollments; only the token owner's submissions are included.")

        bundle = {
            "schema_version": SCHEMA_VERSION,
            "export": None,  # filled below, after hashing the content
            "course": {k: v for k, v in course.items() if k != "syllabus_html"} | {"syllabus_document_id":
                       "DOC-SYLLABUS" if course["syllabus_html"] else None},
            "outcomes": outcomes,
            "modules": modules,
            "assessments": assessments,
            "students": students,
            "submissions": submissions,
            "evidence_refs": self.evidence,
            "documents": documents,
            "resource_chunks": chunks,
            "quality": {
                "outcome_source": outcome_source,
                "scope": "instructor" if instructor_view else "self_only",
                "warnings": self.warnings,
                "counts": {"outcomes": len(outcomes), "modules": len(modules), "assessments": len(assessments),
                           "students": len(students), "submissions": len(submissions),
                           "graded_submissions": sum(s["score"] is not None for s in submissions),
                           "feedback_comments": sum(len(s["feedback"]) for s in submissions),
                           "rubric_notes": sum(1 for s in submissions for r in s["rubric_assessment"] if r["comments"]),
                           "documents": len(documents), "resource_chunks": len(chunks),
                           "evidence_refs": len(self.evidence)},
            },
        }
        content_hash = sha256(json.dumps({k: v for k, v in bundle.items() if k != "export"}, sort_keys=True,
                                         default=str))
        bundle["export"] = {"export_id": self.out_dir.name, "generated_at": now(), "adapter": ADAPTER,
                            "source": {"system": "canvas", "base_url": self.cv.base, "api_version": "v1"},
                            "course_id": self.cid, "content_hash": content_hash, "api_calls": len(self.cv.calls)}
        return bundle


def assessment_type(a: dict, group_name: str) -> str:
    if "online_quiz" in (a.get("submission_types") or []) or a.get("is_quiz_assignment") or a.get("quiz_id"):
        return "quiz"
    label = f"{a.get('name', '')} {group_name}".lower()
    if "exam" in label or "midterm" in label:
        return "exam"
    return "project" if "project" in label else "assignment"


def stated_outcomes(desc_text: str, outcomes: list[dict]) -> list[dict]:
    """Outcomes the instructor listed in the assignment text, e.g. 'Objectives: 1, 2, 6' or 'Objectives: all'."""
    m = re.search(r"(?:Objectives|Outcomes):\s*(all\b|\d+(?:\s*,\s*\d+)*)", desc_text or "", flags=re.I)
    if not m:
        return []
    known = {o["outcome_id"] for o in outcomes}
    ids = sorted(known) if m.group(1).lower() == "all" else [f"LO-{int(n):02d}" for n in re.findall(r"\d+", m.group(1))]
    return [{"outcome_id": i, "provenance": "instructor_stated_in_assignment", "excerpt": m.group(0)}
            for i in ids if i in known]


def export_course(base_url: str, token: str, course_id: str) -> tuple[dict, Path]:
    export_id = f"EXP-{course_id}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    out_dir = EXPORTS / export_id
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = Exporter(Canvas(base_url, token), course_id, out_dir).run()
    path = out_dir / "bundle.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    return bundle, path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    b, p = export_course(os.environ.get("CANVAS_BASE_URL", "http://localhost:8001"),
                         os.environ.get("CANVAS_TOKEN", "dev"), sys.argv[1])
    print(f"Wrote {p}")
    print(json.dumps(b["quality"], indent=2))
