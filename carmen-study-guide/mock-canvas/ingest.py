"""
Canvas -> analytics ingestion bundle (Workstream A of the pipeline spec).

Pulls one course through the Canvas REST API and writes:

    exports/<export_id>/bundle.json           normalized source artifacts (format: INGEST_CONTRACT.md)
    exports/<export_id>/files/<doc_id>.pdf    immutable copies of the original files

The same calls work against this mock and real Canvas, so the mock and real adapters emit the same contract:

    .venv/bin/python ingest.py 1001                      # whole course, mock at http://localhost:8001
    .venv/bin/python ingest.py 1001 2003                 # one assessment + the material related to it
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

import ocr

HERE = Path(__file__).resolve().parent
EXPORTS = HERE / "exports"
SCHEMA_VERSION = "ingest-1.5"
QUESTION_PART = re.compile(r"(FRQ|Part|Question|Q)\s*[\dIVX]")  # rubric rows that are exam questions
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


def quiz_question_catalog(assessment: dict) -> dict[int, dict]:
    """Read stable question numbers, stems and choices from a quiz assignment description."""
    html = assessment.get("description_html") or ""
    matches = list(re.finditer(r"<p><strong>(\d+)\.</strong>(.*?)</p>", html, flags=re.S))
    catalog = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        tail = html[match.end():end]
        catalog[int(match.group(1))] = {
            "question_id": f"Q-{assessment['canvas_id']}-{int(match.group(1)):02d}",
            "question_number": int(match.group(1)),
            "question_text": text_of(match.group(2)),
            "choices": [text_of(choice) for choice in re.findall(r"<li>(.*?)</li>", tail, flags=re.S)],
        }
    return catalog


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
    def __init__(self, canvas: Canvas, course_id: str, out_dir: Path, assessment_id: str | None = None):
        self.cv, self.cid, self.out_dir = canvas, str(course_id), out_dir
        self.only = str(assessment_id) if assessment_id else None  # scope the export to one assessment
        self.files_dir = out_dir / "files"
        self.evidence: list[dict] = []
        self.warnings: list[str] = []
        self.submission_files: list[dict] = []  # student work: instructor + owner only, never indexed
        self.extractions: list[dict] = []

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

    def related(self, a: dict, modules: list[dict]) -> tuple[dict, list[dict], list[int]]:
        """Course material tied to one assessment, each with the rule that matched:
        same_module       - pages/files in the module where the assessment is assigned
        chapter_reference - textbook chapters named in its title, description or its module's headings
        taught_with       - slide decks in the module where a referenced chapter is first taught
        """
        include: dict = {}

        def add(key, rule, detail):
            reason = {"rule": rule, "detail": detail}
            if reason not in include.setdefault(key, []):
                include[key].append(reason)

        ref = {"kind": "assignment", "canvas_id": a["canvas_id"]}
        home = home_module(a, modules)
        chapters = chapter_scope(a, home)

        for m in home:
            for it in m["items"]:
                if it["ref"] and it["ref"]["kind"] in ("page", "file"):
                    add((it["ref"]["kind"], it["ref"]["canvas_id"]), "same_module", m["name"])

        first_taught: dict = {}  # chapter page -> (title, first module it appears in)
        for m in modules:
            for it in m["items"]:
                n = chapter_number(it["title"]) if it["ref"] and it["ref"]["kind"] == "page" else None
                if n is not None:
                    first_taught.setdefault(it["ref"]["canvas_id"], (it["title"], m))
                    if n in chapters:
                        add(("page", it["ref"]["canvas_id"]), "chapter_reference", f"Chapter {n}")

        for key in [k for k in include if k[0] == "page" and k[1] in first_taught]:
            title, m = first_taught[key[1]]
            for it in m["items"]:
                if it["ref"] and it["ref"]["kind"] == "file" and re.search(r"slide|lecture", it["title"], re.I):
                    add(("file", it["ref"]["canvas_id"]), "taught_with", f"{title} ({m['name']})")

        if not include:
            self.warnings.append(f"No course material is linked to {a['name']} by module or chapter reference; "
                                 "the export has its grades and feedback but no resources.")
        return include, home, chapters

    def documents(self, course: dict, where: dict, include: dict | None = None) -> tuple[list[dict], list[dict]]:
        """include=None exports everything; otherwise only the keys in include (from related())."""
        docs, chunks, seen = [], [], set()

        def wanted(key) -> bool:
            return include is None or key in include

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

        def add_html_doc(doc_id, title, doc_type, html, source_type, canvas_id, url, module, status, key=None):
            data = (html or "").encode()
            self.files_dir.mkdir(parents=True, exist_ok=True)
            (self.files_dir / f"{doc_id}.html").write_bytes(data)  # keep the original, like the PDFs
            doc = {"document_id": doc_id, "source_type": source_type, "canvas_id": canvas_id, "title": title,
                   "document_type": doc_type, "module": module, "content_type": "text/html",
                   "size_bytes": len(data), "sha256": sha256(data), "stored_path": f"files/{doc_id}.html",
                   "source_url": url, "page_count": None, "publication_status": status,
                   "access_roles": ["student", "instructor"], "relevance": (include or {}).get(key, [])}
            docs.append(doc)
            for i, (heading, content) in enumerate(html_sections(html), 1):
                add_chunk(doc, i, {"section": heading, "section_index": i}, content, "html")

        if course["syllabus_html"] and wanted(("syllabus", None)):
            add_html_doc("DOC-SYLLABUS", "Syllabus", "syllabus", course["syllabus_html"], "canvas_syllabus",
                         course["canvas_id"], f"{self.cv.base}/courses/{self.cid}/assignments/syllabus", None, "published")

        for p in self.cv.get_all(f"/courses/{self.cid}/pages", optional=True) or []:
            if not wanted(("page", p["url"])):
                continue
            full = self.cv.get_one(f"/courses/{self.cid}/pages/{p['url']}", optional=True)
            if not full:
                self.warnings.append(f"Page '{p['url']}' could not be read.")
                continue
            title = full.get("title") or p["url"]
            doc_type = "syllabus" if p["url"] == "syllabus" else \
                "textbook_section" if re.search(r"textbook|chapter|glossary", title, re.I) else "course_page"
            add_html_doc(f"DOC-PAGE-{p['url']}", title, doc_type, full.get("body"), "canvas_page",
                         full.get("page_id") or p["url"], full.get("html_url"), where.get(("page", p["url"])),
                         published(full), key=("page", p["url"]))

        files = self.cv.get_all(f"/courses/{self.cid}/files", optional=True)
        if files is None:
            self.warnings.append("Course files are not listable with this token; slides and PDFs were skipped.")
        for f in files or []:
            if not wanted(("file", f["id"])):
                continue
            ctype = f.get("content-type") or f.get("content_type") or ""
            module = where.get(("file", f["id"]))
            label = f"{(module or {}).get('item_title', '')} {f['display_name']}"
            doc = {"document_id": f"DOC-{f['id']}", "source_type": "canvas_file", "canvas_id": f["id"],
                   "title": (module or {}).get("item_title") or f["display_name"], "filename": f["display_name"],
                   "document_type": "lecture_slides" if re.search(r"slide|lecture", label, re.I) else "file",
                   "module": module, "content_type": ctype, "size_bytes": f.get("size"), "sha256": None,
                   "stored_path": None, "source_url": f"{self.cv.base}/courses/{self.cid}/files/{f['id']}",
                   "page_count": None, "publication_status": published(f),
                   "access_roles": ["student", "instructor"], "relevance": (include or {}).get(("file", f["id"]), [])}
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

    def assessments(self, outcomes: list[dict], where: dict, modules: list[dict] | None = None) -> list[dict]:
        groups = {g["id"]: g for g in self.cv.get_all(f"/courses/{self.cid}/assignment_groups", optional=True) or []}
        out = []
        source = [self.cv.get_one(f"/courses/{self.cid}/assignments/{self.only}")] if self.only else \
            self.cv.get_all(f"/courses/{self.cid}/assignments") or []
        for a in source:
            group = groups.get(a.get("assignment_group_id"), {})
            desc_text = text_of(a.get("description"))
            kind = assessment_type(a, group.get("name", ""))
            stems = quiz_question_catalog({"description_html": a.get("description"), "canvas_id": a["id"]}) \
                if kind == "quiz" else {}
            out.append({
                "assessment_id": f"A-{a['id']}", "canvas_id": a["id"], "name": a["name"],
                "type": kind,
                "assignment_group": {"canvas_id": group.get("id"), "name": group.get("name"),
                                     "weight_percent": group.get("group_weight")} if group else None,
                "module": where.get(("assignment", a["id"])),
                "points_possible": a.get("points_possible"), "due_at": a.get("due_at"),
                "unlock_at": a.get("unlock_at"), "submission_types": a.get("submission_types"),
                "description_html": a.get("description"), "description_text": desc_text or None,
                "rubric": [{"criterion_id": r["id"], "description": r.get("description"),
                            "long_description": r.get("long_description"), "points": r.get("points"),
                            "kind": "question_part" if QUESTION_PART.match(r.get("description") or "")
                            else "rubric_dimension"}
                           for r in a.get("rubric") or []],
                "stated_outcome_ids": stated_outcomes(desc_text, outcomes),
                "questions": list(stems.values()),  # quiz stems and choices; answers never appear here
                "chapters_covered": chapter_scope({"name": a["name"], "description_text": desc_text},
                                                  home_module({"canvas_id": a["id"]}, modules or [])),
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

    def question_responses(self, assessment: dict, submission: dict, instructor_view: bool,
                           api_path: str) -> list[dict]:
        if assessment.get("type") != "quiz":
            return []
        questions = quiz_question_catalog(assessment)
        raw_items = submission.get("quiz_responses") or []
        # Read the older local mock shape during the contract transition.
        if isinstance(raw_items, dict):
            raw_items = [{"question_number": number, "answer_index": response.get("selected_index"),
                          "correct_answer_index": response.get("correct_index"), "response_text": response.get("text"),
                          "points_earned": response.get("earned"), "points_possible": response.get("possible")}
                         for number, response in raw_items.items()]
        if not raw_items and isinstance(submission.get("responses"), dict):
            raw_items = [{"question_number": number, "answer_index": response.get("selected_index"),
                          "correct_answer_index": response.get("correct_index"), "response_text": response.get("text"),
                          "points_earned": response.get("earned"), "points_possible": response.get("possible")}
                         for number, response in submission["responses"].items()]

        out = []
        for raw in raw_items:
            number = int(raw.get("question_number", 0))
            question = questions.get(number, {})
            question_id = raw.get("question_id") or question.get("question_id") or \
                f"Q-{assessment['canvas_id']}-{number:02d}"
            answer_index = raw.get("answer_index", raw.get("selected_index"))
            correct_index = raw.get("correct_answer_index", raw.get("correct_index"))
            choices = question.get("choices", [])
            if answer_index is not None:
                answer = {"choice_index": answer_index,
                          "text": choices[answer_index] if 0 <= answer_index < len(choices) else None}
            else:
                answer = {"text": raw.get("response_text", raw.get("text"))}
            correct = raw.get("correct")
            if correct is None and answer_index is not None and correct_index is not None:
                correct = answer_index == correct_index
            item = {
                "question_id": question_id,
                "question_number": number,
                "question_text": question.get("question_text") or None,
                "response": answer,
                "correct": correct,
                "points_earned": raw.get("points_earned", raw.get("earned")),
                "points_possible": raw.get("points_possible", raw.get("possible")),
                "comments": (raw.get("comments") or "").strip() or None,
            }
            if instructor_view and correct_index is not None:
                item["correct_answer"] = {
                    "choice_index": correct_index,
                    "text": choices[correct_index] if 0 <= correct_index < len(choices) else None,
                    "access_roles": ["instructor"],
                }
            excerpt = f"Question: {item['question_text'] or question_id}\nResponse: {answer.get('text') or '(choice not found)'}"
            if item["points_earned"] is not None:
                excerpt += f"\nPoints: {item['points_earned']}/{item['points_possible']}"
            item["evidence_ref_id"] = self.evidence_ref(
                "canvas_quiz_response", api_path, excerpt, submission_id=submission.get("id"),
                question_id=question_id, attempt_id=submission.get("attempt"))
            item["comment_evidence_ref_id"] = self.evidence_ref(
                "canvas_quiz_question_comment", api_path, item["comments"], submission_id=submission.get("id"),
                question_id=question_id) if item["comments"] else None
            item["source_ref"] = {"api_path": api_path, "canvas_submission_id": submission.get("id"),
                                  "question_id": question_id}
            out.append(item)
        return out

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
                attempt_id = str(s["attempt"]) if s.get("attempt") is not None else None
                submission_id = f"SUB-{a['canvas_id']}-{student}"
                if attempt_id:
                    submission_id += f"-A{attempt_id}"
                attachments = [self.attachment(att, a, student, submission_id) for att in s.get("attachments") or []]
                extracted = "\n\n".join(x["text"] for x in self.extractions
                                         if x["submission_id"] == submission_id and x["text"]) or None
                out.append({
                    "submission_id": submission_id, "canvas_id": s.get("id"),
                    "assessment_id": a["assessment_id"], "student_id": student,
                    "attempt_id": attempt_id,
                    "workflow_state": s.get("workflow_state"), "late": s.get("late"), "missing": s.get("missing"),
                    "submitted_at": s.get("submitted_at"), "graded_at": s.get("graded_at"),
                    "score": s.get("score"), "points_possible": a["points_possible"],
                    "response": {"submission_type": s.get("submission_type"), "body_text": body or None,
                                 "attachments": attachments, "extracted_text": extracted},
                    "question_responses": self.question_responses(a, s, instructor_view, path),
                    "rubric_assessment": rubric, "feedback": feedback,
                    "source_ref": {"api_path": path},
                })
        return out

    def attachment(self, att: dict, a: dict, student: str, sub_id: str) -> dict:
        """Download one submitted file, keep the original, and extract its text (native text layer or OCR)."""
        doc_id = f"SUBDOC-{att.get('id')}"
        ctype = att.get("content-type") or att.get("content_type") or ""
        ref = {"canvas_file_id": att.get("id"), "document_id": doc_id, "filename": att.get("filename"),
               "content_type": ctype, "upload_source": att.get("upload_source")}
        if (att.get("size") or 0) > MAX_FILE_BYTES:
            self.warnings.append(f"{a['name']}: {att.get('filename')} is too large to analyze.")
            return ref
        try:
            data = self.cv.download(att["url"])
        except requests.RequestException as e:
            self.warnings.append(f"{a['name']}: couldn't download {att.get('filename')} ({e}).")
            return ref
        ext = Path(att.get("filename") or "").suffix or ".bin"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        (self.files_dir / f"{doc_id}{ext}").write_bytes(data)
        digest = sha256(data)
        self.submission_files.append({
            "document_id": doc_id, "canvas_file_id": att.get("id"), "submission_id": sub_id,
            "assessment_id": a["assessment_id"], "student_id": student, "filename": att.get("filename"),
            "content_type": ctype, "size_bytes": len(data), "sha256": digest, "stored_path": f"files/{doc_id}{ext}",
            "upload_source": att.get("upload_source"), "uploaded_at": att.get("created_at"),
            "access_roles": ["instructor", "owner"]})
        if ctype == "application/pdf" or ctype.startswith("image/"):
            try:
                r = ocr.analyze(data, ctype, digest.split(":", 1)[1])
            except Exception as e:
                self.warnings.append(f"{a['name']}: text extraction failed for {att.get('filename')} ({e}).")
                return ref
            self.extractions.append({
                "extraction_id": f"EXT-{att.get('id')}", "document_id": doc_id, "submission_id": sub_id,
                "assessment_id": a["assessment_id"], "student_id": student, **r,
                "text": "\n\n".join(pg["text"] for pg in r["pages"] if pg["text"])})
            if r["flags"]:
                self.warnings.append(f"{a['name']} ({student}): {att.get('filename')} flagged "
                                     f"{', '.join(r['flags'])}; check the extracted text against the original.")
        return ref

    # ---- bundle

    def run(self) -> dict:
        course = self.course()
        outcomes, outcome_source = self.outcomes(course["syllabus_html"])
        modules, where = self.modules()
        assessments = self.assessments(outcomes, where, modules)
        scope = {"level": "course"}
        include = None
        if self.only:
            a = assessments[0]
            include, home, chapters = self.related(a, modules)
            modules = home
            scope = {"level": "assessment", "assessment_id": a["assessment_id"], "assessment_name": a["name"],
                     "assessment_type": a["type"], "home_module": home[0]["name"] if home else None,
                     "chapters_referenced": chapters,
                     "rules": ["same_module", "chapter_reference", "taught_with"]}
        documents, chunks = self.documents(course, where, include)
        students, instructor_view = self.students()
        submissions = self.submissions(assessments, instructor_view)
        if self.only or not students:  # scoped: only the students with work on this assessment
            students = [{"student_id": sid, "enrollment_state": next(
                            (s["enrollment_state"] for s in students if s["student_id"] == sid), None)}
                        for sid in dict.fromkeys(s["student_id"] for s in submissions)]

        if os.environ.get("ANON_SALT", DEV_SALT) == DEV_SALT:
            self.warnings.append("ANON_SALT is not set; pseudonyms use the development salt.")
        has_question_responses = any(s["question_responses"] for s in submissions)
        has_submission_bodies = any(s["response"]["body_text"] or s["response"]["attachments"] for s in submissions)
        if submissions and not has_question_responses and not has_submission_bodies:
            self.warnings.append("No submission bodies, attachments or quiz item responses were available; "
                                 "evidence is assignment- and rubric-level.")
        elif has_question_responses and not has_submission_bodies:
            self.warnings.append("Graded quiz item responses are available; non-quiz submission bodies and "
                                 "attachments are not present.")
        if not instructor_view:
            self.warnings.append("Token can't list course enrollments; only the token owner's submissions are included.")

        bundle = {
            "schema_version": SCHEMA_VERSION,
            "export": None,  # filled below, after hashing the content
            "scope": scope,
            "course": {k: v for k, v in course.items() if k != "syllabus_html"} | {"syllabus_document_id":
                       "DOC-SYLLABUS" if any(d["document_id"] == "DOC-SYLLABUS" for d in documents) else None},
            "outcomes": outcomes,
            "modules": modules,
            "assessments": assessments,
            "students": students,
            "submissions": submissions,
            "evidence_refs": self.evidence,
            "submission_files": self.submission_files,  # student work: instructor + owner only
            "extractions": self.extractions,
            "documents": documents,
            "resource_chunks": chunks,
            "quality": {
                "outcome_source": outcome_source,
                "scope": "instructor" if instructor_view else "self_only",
                "warnings": self.warnings,
                "counts": {"outcomes": len(outcomes), "modules": len(modules), "assessments": len(assessments),
                           "students": len(students), "submissions": len(submissions),
                           "graded_submissions": sum(s["score"] is not None for s in submissions),
                           "question_responses": sum(len(s["question_responses"]) for s in submissions),
                           "feedback_comments": sum(len(s["feedback"]) for s in submissions),
                           "rubric_notes": sum(1 for s in submissions for r in s["rubric_assessment"] if r["comments"]),
                           "submission_files": len(self.submission_files),
                           "extracted_pages": sum(x["page_count"] for x in self.extractions),
                           "flagged_extractions": sum(1 for x in self.extractions if x["flags"]),
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


def chapter_refs(text: str) -> list[int]:
    """Chapter numbers named in text: 'Chapter 5', 'Chapters 1–4', 'Ch. 2', 'Chapters 3 to 6'."""
    found: set[int] = set()
    for m in re.finditer(r"\b(?:Chapters?|Ch\.)\s*(\d+)(?:\s*(?:[–—-]|to|through)\s*(\d+))?", text or "", flags=re.I):
        lo, hi = sorted((int(m.group(1)), int(m.group(2) or m.group(1))))
        if hi - lo <= 30:
            found.update(range(lo, hi + 1))
    return sorted(found)


def home_module(a: dict, modules: list[dict]) -> list[dict]:
    """The module where an assessment is first placed (its week), as a 0- or 1-item list."""
    ref = {"kind": "assignment", "canvas_id": a["canvas_id"]}
    return [m for m in modules if any(it["ref"] == ref for it in m["items"])][:1]


def chapter_scope(a: dict, home: list[dict]) -> list[int]:
    """Chapters an assessment covers, as named in its title, description or its module's headings."""
    text = " ".join([a["name"], a.get("description_text") or ""] +
                    [it["title"] for m in home for it in m["items"] if it["type"] == "SubHeader"])
    return chapter_refs(text)


def chapter_number(title: str) -> int | None:
    m = re.search(r"\bChapter\s+(\d+)\b", title or "", flags=re.I)
    return int(m.group(1)) if m else None


def export_course(base_url: str, token: str, course_id: str, assessment_id: str | None = None,
                  root: Path = EXPORTS) -> tuple[dict, Path]:
    """Export a whole course, or (with assessment_id) one assessment and the material related to it."""
    scope = f"-A{assessment_id}" if assessment_id else ""
    export_id = f"EXP-{course_id}{scope}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}"
    out_dir = root / export_id
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = Exporter(Canvas(base_url, token), course_id, out_dir, assessment_id).run()
    path = out_dir / "bundle.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle, path


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    b, p = export_course(os.environ.get("CANVAS_BASE_URL", "http://localhost:8001"),
                         os.environ.get("CANVAS_TOKEN", "dev"), sys.argv[1], (sys.argv[2:] or [None])[0])
    print(f"Wrote {p}")
    print(json.dumps(b["quality"], indent=2))
