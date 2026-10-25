"""
Store an ingestion bundle (ingest.py) in the team's Supabase Postgres, using the service role.
sync.py calls this on every course page load so the database mirrors the mock Carmen site.

Writes source facts only: course, pseudonymous learners, outcomes, documents (originals uploaded to the
private 'course-materials' bucket), resource chunks, assessments, questions, attempts, responses,
evidence refs and feedback. LERs, ARRs and IRs come from later pipeline stages.

Safe to re-run:
- Same export again: nothing changes.
- Changed grade or rubric: the response row is updated, and the lineage trigger marks dependent ARRs stale.
- Changed document: a new document row is added, and the old version's chunks are hidden from retrieval.

Assignment-level evidence (overall score, rubric, comments) hangs off one question per assessment with
code 'WHOLE' and question_type 'assignment_level'. Exams also get real per-part questions from their rubric.
Quiz attempts use one question and response row per quiz item. Instructor answer keys go only to the
staff-protected question_answer_keys table; they are never copied into resource chunks.

    .venv/bin/python db_store.py exports/<export_id>/bundle.json
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from supabase_client import SERVICE_KEY_NAMES, service_client

BUCKET = "course-materials"
WHOLE = "WHOLE"
DOC_TYPES = {"syllabus": "syllabus", "lecture_slides": "slides", "textbook_section": "textbook",
             "course_page": "reading", "file": "other"}
ASSESSMENT_TYPES = {"assignment": "homework", "quiz": "quiz", "exam": "exam", "project": "project"}
BATCH = 500


def configured() -> str | None:
    """None when the service key is set, else the reason storing is skipped."""
    if any(os.environ.get(n, "") not in ("", "REPLACE_ME") for n in SERVICE_KEY_NAMES):
        return None
    return "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) is not set in mock-canvas/.env"


def _hex(h: str | None) -> str | None:
    return h.split(":", 1)[-1] if h else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _canvas_ref(evidence: dict) -> str:
    ids = "&".join(f"{key}={value}" for key, value in evidence["canvas_ids"].items())
    return f"{evidence['api_path']}#{ids}"


class Store:
    def __init__(self, bundle: dict, export_dir: Path):
        self.b, self.dir = bundle, Path(export_dir)
        self.db = service_client()
        base = bundle["export"]["source"]["base_url"]
        self.source = "mock" if re.search(r"//(localhost|127\.0\.0\.1)(:|/|$)", base) else "canvas"
        self.counts: dict[str, int] = {}

    def _count(self, key: str, n: int):
        self.counts[key] = self.counts.get(key, 0) + n

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> list[dict]:
        if not rows:
            return []
        out = []
        for i in range(0, len(rows), BATCH):
            out += self.db.table(table).upsert(rows[i:i + BATCH], on_conflict=on_conflict).execute().data
        self._count(table, len(out))
        return out

    def select_all(self, table: str, columns: str, **eq) -> list[dict]:
        """Every matching row, paging past PostgREST's 1000-row default limit."""
        out, start = [], 0
        while True:
            q = self.db.table(table).select(columns)
            for k, v in eq.items():
                q = q.eq(k, v)
            page = q.range(start, start + 999).execute().data
            out += page
            if len(page) < 1000:
                return out
            start += 1000

    def insert(self, table: str, rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        out = []
        for i in range(0, len(rows), BATCH):
            out += self.db.table(table).insert(rows[i:i + BATCH]).execute().data
        self._count(table, len(out))
        return out

    # ---------------------------------------------------------------- steps

    def course(self):
        c = self.b["course"]
        row = self.upsert("courses", [{"code": c["course_code"] or c["name"], "title": c["name"],
                                       "canvas_id": str(c["canvas_id"])}], "code")[0]
        self.cid, self.course_slug = row["id"], _slug(row["code"])

    def learners(self):
        rows = self.upsert("learners", [{"course_id": self.cid, "pseudonym": s["student_id"]}
                                        for s in self.b["students"]], "course_id,pseudonym")
        self.learner = {r["pseudonym"]: r["id"] for r in rows}

    def documents(self):
        rows, by_sha = [], {}
        for d in self.b["documents"]:
            sha = _hex(d["sha256"])
            if not sha or sha in by_sha or not d.get("stored_path"):
                continue  # not downloaded, or identical content already registered
            ext = Path(d["stored_path"]).suffix
            path = f"{self.course_slug}/{sha}{ext}"
            self.db.storage.from_(BUCKET).upload(path, (self.dir / d["stored_path"]).read_bytes(),
                                                 {"content-type": d.get("content_type") or "application/octet-stream",
                                                  "upsert": "true"})
            self._count("files_uploaded", 1)
            by_sha[sha] = {
                "course_id": self.cid, "title": d["title"], "doc_type": DOC_TYPES.get(d["document_type"], "other"),
                "storage_bucket": BUCKET, "storage_path": path, "sha256": sha, "mime_type": d.get("content_type"),
                "page_count": d.get("page_count"), "canvas_id": f"{d['source_type']}:{d['canvas_id']}",
                "learner_id": None,
                "publication_status": "released" if d["publication_status"] == "published" else "draft",
                # Mock content is synthetic; real course material needs an instructor to clear rights.
                "rights_cleared": self.source == "mock",
            }
        saved = {r["sha256"]: r for r in self.upsert("documents", list(by_sha.values()), "course_id,sha256")}
        self.doc = {d["document_id"]: saved[_hex(d["sha256"])] for d in self.b["documents"]
                    if _hex(d["sha256"]) in saved}

        # A document whose content changed got a new row: hide the old version's chunks from retrieval.
        current_ids = {r["id"] for r in saved.values()}
        canvas_ids = [r["canvas_id"] for r in saved.values()]
        old = self.db.table("documents").select("id").eq("course_id", self.cid).in_("canvas_id", canvas_ids) \
            .execute().data if canvas_ids else []
        old_ids = [o["id"] for o in old if o["id"] not in current_ids]
        if old_ids:
            self.db.table("resource_chunks").update({"student_visible": False, "publication_status": "restricted"}) \
                .in_("document_id", old_ids).execute()
            self._count("superseded_documents", len(old_ids))

    def chunks(self):
        doc_ids = list({r["id"] for r in self.doc.values()})
        have = {r["document_id"] for r in self.db.table("resource_chunks").select("document_id")
                .in_("document_id", doc_ids).execute().data} if doc_ids else set()
        rows = []
        for ch in self.b["resource_chunks"]:
            doc = self.doc.get(ch["document_id"])
            if not doc or doc["id"] in have:
                continue  # this document version is already indexed
            loc = ch["locator"]
            slides = ch["document_type"] == "lecture_slides"
            rows.append({
                "course_id": self.cid, "document_id": doc["id"], "title": ch["title"], "content": ch["content"],
                "doc_type": DOC_TYPES.get(ch["document_type"], "other"), "page": loc.get("page"),
                "slide": loc.get("page") if slides else None, "section": loc.get("section"),
                "deep_link": ch["deep_link"], "publication_status": doc["publication_status"],
                "student_visible": doc["publication_status"] == "released" and "student" in ch["access_roles"],
                "extraction_version": ch["extraction"]["version"],
            })
        self.insert("resource_chunks", rows)

    def outcomes(self):
        syllabus = self.doc.get(self.b["course"].get("syllabus_document_id"))
        # An assessment-scoped export has no syllabus document: leave the stored link alone rather than null it.
        link = {"source_document_id": syllabus["id"]} if syllabus else {}
        rows = self.upsert("outcomes", [{"course_id": self.cid, "code": o["outcome_id"], "syllabus_text": o["text"],
                                         "instructor_verified": o["instructor_verified"], **link}
                                        for o in self.b["outcomes"]], "course_id,code")
        self.outcome = {r["code"]: r["id"] for r in rows}

    def assessments(self):
        rows, seen = [], set()
        for a in self.b["assessments"]:
            code = a["name"].split(":")[0].strip()[:60]
            if code in seen:
                code = a["assessment_id"]
            seen.add(code)
            a["_code"] = code
            # integrity_status / answers_released are instructor policy: left at their defaults on insert,
            # never overwritten here.
            rows.append({"course_id": self.cid, "code": code, "title": a["name"],
                         "assessment_type": ASSESSMENT_TYPES[a["type"]], "due_at": a["due_at"],
                         "canvas_id": str(a["canvas_id"])})
        saved = {r["code"]: r["id"] for r in self.upsert("assessments", rows, "course_id,code")}
        self.assessment = {a["assessment_id"]: saved[a["_code"]] for a in self.b["assessments"]}

    def questions(self):
        rows, quiz_items = [], {}
        instructor_scope = self.b.get("quality", {}).get("scope") == "instructor"
        for a in self.b["assessments"]:
            aid = self.assessment[a["assessment_id"]]
            if a["type"] == "quiz":
                for s in self.b["submissions"]:
                    if s["assessment_id"] != a["assessment_id"]:
                        continue
                    for item in s.get("question_responses", []):
                        qid = str(item["question_id"])
                        quiz_items.setdefault((aid, qid), item)
                choices = {q["question_number"]: [{"text": c} for c in q["choices"]] for q in a.get("questions", [])}
                for (question_assessment_id, qid), item in quiz_items.items():
                    if question_assessment_id != aid:
                        continue
                    rows.append({"course_id": self.cid, "assessment_id": aid, "code": f"Q{item.get('question_number')}",
                                 "position": item.get("question_number"), "text": item.get("question_text"),
                                 "question_type": "quiz_item", "points_possible": item.get("points_possible"),
                                 "canvas_id": qid,
                                 "locator": {"canvas_api": a["source_ref"]["api_path"],
                                             "question_id": qid,
                                             "choices": choices.get(item.get("question_number"), [])}})
                if not any(question_assessment_id == aid for question_assessment_id, _ in quiz_items):
                    rows.append({"course_id": self.cid, "assessment_id": aid, "code": WHOLE, "position": 0,
                                 "text": a["description_text"], "question_type": "assignment_level",
                                 "points_possible": a["points_possible"], "canvas_id": str(a["canvas_id"]),
                                 "locator": {"canvas_api": a["source_ref"]["api_path"], "scope": "assessment",
                                             "chapters_covered": a.get("chapters_covered", [])}})
            else:
                rows.append({"course_id": self.cid, "assessment_id": aid, "code": WHOLE, "position": 0,
                             "text": a["description_text"], "question_type": "assignment_level",
                             "points_possible": a["points_possible"], "canvas_id": str(a["canvas_id"]),
                             "locator": {"canvas_api": a["source_ref"]["api_path"], "scope": "assessment",
                                             "chapters_covered": a.get("chapters_covered", [])}})
                for i, r in enumerate((r for r in a["rubric"] if r["kind"] == "question_part"), 1):
                    rows.append({"course_id": self.cid, "assessment_id": aid,
                                 "code": r["description"].split(":")[0].strip()[:60], "position": i,
                                 "text": r["description"], "question_type": "rubric_question_part",
                                 "points_possible": r["points"], "canvas_id": r["criterion_id"],
                                 "locator": {"canvas_api": a["source_ref"]["api_path"],
                                             "rubric_criterion_id": r["criterion_id"]}})
        saved = self.upsert("questions", rows, "assessment_id,code")
        self.question = {(r["assessment_id"], r["canvas_id"] if r["code"] != WHOLE else WHOLE): r["id"]
                         for r in saved}

        # The answer key is intentionally kept out of the ordinary questions and retrieval tables.
        answer_keys = []
        if instructor_scope:
            for (aid, qid), item in quiz_items.items():
                key = item.get("correct_answer")
                question_id = self.question.get((aid, qid))
                if key is not None and question_id:
                    answer_keys.append({"question_id": question_id, "course_id": self.cid,
                                        "answer": json.dumps(key, ensure_ascii=False)})
        self.upsert("question_answer_keys", answer_keys, "question_id")

        # Outcomes the instructor stated in the assignment text apply to its assignment-level question.
        links = []
        for a in self.b["assessments"]:
            aid = self.assessment[a["assessment_id"]]
            targets = [qid for (question_aid, qid) in quiz_items if question_aid == aid]
            if not targets:
                targets = [WHOLE]
            for outcome in a["stated_outcome_ids"]:
                if outcome["outcome_id"] not in self.outcome:
                    continue
                for target in targets:
                    links.append({"question_id": self.question[(aid, target)],
                                  "outcome_id": self.outcome[outcome["outcome_id"]],
                                  "provenance": "instructor", "confidence": None,
                                  "rationale": outcome["excerpt"], "needs_review": False})
        self.upsert("question_outcomes", links, "question_id,outcome_id")

    def submissions(self):
        evidence = {e["id"]: e for e in self.b["evidence_refs"]}
        attempts = []
        for s in self.b["submissions"]:
            if s["attempt_id"] is None:
                continue  # never submitted: no attempt to record
            attempts.append({"course_id": self.cid, "assessment_id": self.assessment[s["assessment_id"]],
                             "learner_id": self.learner[s["student_id"]], "attempt_number": int(s["attempt_id"]),
                             "submitted_at": s["submitted_at"], "canvas_id": str(s["canvas_id"])})
        saved = self.upsert("attempts", attempts, "assessment_id,learner_id,attempt_number")
        attempt = {(r["assessment_id"], r["learner_id"], int(r["attempt_number"])): r["id"] for r in saved}

        responses = []
        for s in self.b["submissions"]:
            aid, lid = self.assessment[s["assessment_id"]], self.learner[s["student_id"]]
            number = int(s["attempt_id"] or 1)
            att = attempt.get((aid, lid, number))
            if not att:
                continue
            # evidence_ref_id is export-local; leave it out so re-exports don't look like grade changes
            rubric = [{k: v for k, v in r.items() if k != "evidence_ref_id"} for r in s["rubric_assessment"]]
            base = {"course_id": self.cid, "attempt_id": att, "learner_id": lid}
            question_responses = s.get("question_responses", [])
            whole_question_id = self.question.get((aid, WHOLE))
            if whole_question_id:
                text = s["response"]["body_text"] or s["response"].get("extracted_text")
                ocr = [{"document_id": x["document_id"], "page": pg["page"], "method": pg["method"],
                        "mean_confidence": pg["mean_confidence"], "flags": pg["flags"]}
                       for x in self.b.get("extractions", []) if x["submission_id"] == s["submission_id"]
                       for pg in x["pages"]]
                responses.append({**base, "question_id": whole_question_id,
                                  "response_text": text, "points_earned": s["score"], "rubric": rubric,
                                  "content_hash": _hash(text, s["score"], rubric),
                                  "locator": {"canvas_api": s["source_ref"]["api_path"],
                                              "attachments": s["response"]["attachments"], "extraction": ocr}})
            for item in question_responses:
                qid = self.question.get((aid, str(item["question_id"])))
                if not qid:
                    continue
                answer = item.get("response") or {}
                answer_text = answer.get("text")
                item_evidence = evidence.get(item.get("evidence_ref_id"))
                item_rubric = {"correct": item.get("correct"),
                               "points_possible": item.get("points_possible")}
                responses.append({**base, "question_id": qid, "response_text": answer_text,
                                  "points_earned": item.get("points_earned"), "rubric": item_rubric,
                                  "content_hash": _hash(answer_text, item.get("points_earned"), item_rubric),
                                  "locator": {"canvas_api": s["source_ref"]["api_path"],
                                              "canvas_submission_id": s["canvas_id"],
                                              "question_id": item["question_id"],
                                              "evidence_ref_id": item.get("evidence_ref_id"),
                                              "canvas_ref": _canvas_ref(item_evidence) if item_evidence else None,
                                              "evidence_content_hash": _hex(item_evidence.get("content_hash"))
                                              if item_evidence else None}})
            for r in rubric:
                qid = self.question.get((aid, r["criterion_id"]))
                if qid and r["kind"] == "question_part":
                    responses.append({**base, "question_id": qid, "response_text": None,
                                      "points_earned": r["points"], "rubric": [r], "content_hash": _hash(None, r["points"], [r]),
                                      "locator": {"canvas_api": s["source_ref"]["api_path"],
                                                  "rubric_criterion_id": r["criterion_id"]}})
        saved = self.upsert("responses", responses, "attempt_id,question_id")
        self.response = {(r["attempt_id"], r["question_id"]): r["id"] for r in saved}
        self.attempt = attempt
        self.response_for_attempt = {}
        for s in self.b["submissions"]:
            aid, lid = self.assessment[s["assessment_id"]], self.learner[s["student_id"]]
            att = attempt.get((aid, lid, int(s["attempt_id"] or 1)))
            if not att:
                continue
            whole = self.question.get((aid, WHOLE))
            response_id = self.response.get((att, whole)) if whole else None
            if response_id is None:
                for item in s.get("question_responses", []):
                    qid = self.question.get((aid, str(item["question_id"])))
                    response_id = self.response.get((att, qid)) if qid else None
                    if response_id:
                        break
            if response_id:
                self.response_for_attempt[att] = response_id

    def feedback(self):
        """One evidence ref + one feedback row per grader comment / rubric note; existing ones are kept."""
        evidence = {e["id"]: e for e in self.b["evidence_refs"]}
        existing = {(r["canvas_ref"], r["content_hash"]) for r in
                    self.select_all("evidence_refs", "canvas_ref,content_hash", course_id=self.cid, source_type="canvas_api")}
        question_evidence = []
        for s in self.b["submissions"]:
            lid = self.learner[s["student_id"]]
            for item in s.get("question_responses", []):
                ev = evidence.get(item.get("evidence_ref_id"))
                if not ev:
                    continue
                ref, content_hash = _canvas_ref(ev), _hex(ev.get("content_hash"))
                if (ref, content_hash) in existing:
                    continue
                existing.add((ref, content_hash))
                question_evidence.append({"course_id": self.cid, "learner_id": lid, "source_type": "canvas_api",
                                          "canvas_ref": ref, "excerpt": ev["excerpt"],
                                          "content_hash": content_hash})
        self.insert("evidence_refs", question_evidence)
        pending = []  # (evidence row, feedback row without evidence id)
        for s in self.b["submissions"]:
            aid, lid = self.assessment[s["assessment_id"]], self.learner[s["student_id"]]
            att = self.attempt.get((aid, lid, int(s["attempt_id"] or 1)))
            if not att:
                continue
            whole = self.response_for_attempt.get(att)
            if not whole:
                continue
            items = [(f, "canvas_comment", whole) for f in s["feedback"] if f["author_role"] == "grader"]
            for r in s["rubric_assessment"]:
                if r["evidence_ref_id"]:
                    part = self.question.get((aid, r["criterion_id"])) if r["kind"] == "question_part" else None
                    items.append(({"text": r["comments"], "evidence_ref_id": r["evidence_ref_id"], "created_at": None},
                                  "rubric_note", self.response.get((att, part)) if part else whole))
            for item in s.get("question_responses", []):  # per-question grader comments on quiz items
                rid = self.response.get((att, self.question.get((aid, str(item["question_id"])))))
                if item.get("comment_evidence_ref_id") and rid:
                    items.append(({"text": item["comments"], "evidence_ref_id": item["comment_evidence_ref_id"],
                                   "created_at": None}, "comment", rid))
            for f, kind, response_id in items:
                ev = evidence[f["evidence_ref_id"]]
                ref, content_hash = _canvas_ref(ev), _hex(ev["content_hash"])
                if (ref, content_hash) in existing:
                    continue
                existing.add((ref, content_hash))
                pending.append(({"course_id": self.cid, "learner_id": lid, "source_type": "canvas_api",
                                 "canvas_ref": ref, "excerpt": ev["excerpt"], "content_hash": content_hash},
                                {"course_id": self.cid, "response_id": response_id, "learner_id": lid, "kind": kind,
                                 "text": f["text"], **({"created_at": f["created_at"]} if f.get("created_at") else {})}))
        if not pending:
            return
        refs = self.insert("evidence_refs", [e for e, _ in pending])
        with_dates = [{**fb, "evidence_ref_id": ref["id"]} for (_, fb), ref in zip(pending, refs) if "created_at" in fb]
        without = [{**fb, "evidence_ref_id": ref["id"]} for (_, fb), ref in zip(pending, refs) if "created_at" not in fb]
        self.insert("feedback", with_dates)  # separate batches: every row in a batch needs the same columns
        self.insert("feedback", without)

    def scans(self):
        """Submitted files: original to the private source-files bucket, one evidence ref per extracted line."""
        files = self.b.get("submission_files", [])
        if not files:
            return
        rows = {}
        for f in files:
            sha = _hex(f["sha256"])
            ext = Path(f["stored_path"]).suffix
            path = f"{self.course_slug}/submissions/{sha}{ext}"
            self.db.storage.from_("source-files").upload(path, (self.dir / f["stored_path"]).read_bytes(),
                                                         {"content-type": f["content_type"] or "application/octet-stream",
                                                          "upsert": "true"})
            self._count("files_uploaded", 1)
            extraction = next((x for x in self.b.get("extractions", []) if x["document_id"] == f["document_id"]), {})
            rows[sha] = {"course_id": self.cid, "title": f"{f['filename']} ({f['assessment_id']})",
                         "doc_type": "submission_scan", "storage_bucket": "source-files", "storage_path": path,
                         "sha256": sha, "mime_type": f["content_type"], "page_count": extraction.get("page_count"),
                         "canvas_id": f"canvas_attachment:{f['canvas_file_id']}",
                         "learner_id": self.learner[f["student_id"]],
                         "publication_status": "restricted", "rights_cleared": False}
        saved = {r["sha256"]: r["id"] for r in self.upsert("documents", list(rows.values()), "course_id,sha256")}

        existing = {(r["canvas_ref"], r["content_hash"])
                    for r in self.select_all("evidence_refs", "canvas_ref,content_hash", course_id=self.cid)}
        refs = []
        for x in self.b.get("extractions", []):
            f = next(f for f in files if f["document_id"] == x["document_id"])
            sha = _hex(f["sha256"])
            source = "image" if (f["content_type"] or "").startswith("image/") else "pdf"
            for pg in x["pages"]:
                for i, line in enumerate(pg["lines"], 1):
                    ref, h = f"{x['extractor_version']}:{sha}#page={pg['page']}&line={i}", _hash(line["text"])
                    if (ref, h) in existing:
                        continue
                    refs.append({"course_id": self.cid, "learner_id": self.learner[f["student_id"]],
                                 "source_type": source, "document_id": saved[sha], "canvas_ref": ref,
                                 "page": pg["page"], "bbox_norm": line["bbox_norm"], "excerpt": line["text"],
                                 "content_hash": h})
        self.insert("evidence_refs", refs)

    # ---------------------------------------------------------------- run

    def unchanged(self) -> bool:
        """True when the last successful whole-course sync stored exactly this content."""
        jobs = self.db.table("ingestion_jobs").select("input").eq("course_id", self.cid).eq("kind", "ingest") \
            .eq("status", "succeeded").order("created_at", desc=True).limit(25).execute().data
        last = next((j for j in jobs if (j["input"].get("scope") or {}).get("level") == "course"), None)
        return bool(last) and last["input"].get("content_hash") == self.b["export"]["content_hash"]

    def run(self, skip_if_unchanged: bool = False) -> dict:
        self.course()
        if skip_if_unchanged and self.b.get("scope", {}).get("level") == "course" and self.unchanged():
            return {"status": "unchanged", "course_db_id": self.cid}
        exp = self.b["export"]
        job = self.db.table("ingestion_jobs").insert({
            "course_id": self.cid, "source": self.source, "kind": "ingest", "status": "running", "attempts": 1,
            "input": {"export_id": exp["export_id"], "content_hash": exp["content_hash"],
                      "scope": self.b.get("scope", {"level": "course"}),
                      "base_url": exp["source"]["base_url"], "schema_version": self.b["schema_version"]},
        }).execute().data[0]
        try:
            for step in (self.learners, self.documents, self.chunks, self.outcomes, self.assessments,
                         self.questions, self.submissions, self.feedback, self.scans):
                step()
        except Exception as e:
            self.db.table("ingestion_jobs").update({"status": "failed", "error": str(e)[:2000],
                                                    "updated_at": _now()}).eq("id", job["id"]).execute()
            raise
        output = {"export_id": exp["export_id"], "rows_written": self.counts}
        self.db.table("ingestion_jobs").update({"status": "succeeded", "output": output, "updated_at": _now()}) \
            .eq("id", job["id"]).execute()
        self.db.table("audit_events").insert({"course_id": self.cid, "event": "ingest.stored",
                                              "entity": "ingestion_jobs", "entity_id": job["id"],
                                              "detail": output}).execute()
        return {"status": "stored", "job_id": job["id"], "course_db_id": self.cid, "rows_written": self.counts}


def store_export(bundle: dict, export_dir: Path, skip_if_unchanged: bool = False) -> dict:
    reason = configured()
    if reason:
        return {"status": "skipped", "reason": reason}
    return Store(bundle, export_dir).run(skip_if_unchanged)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    p = Path(sys.argv[1])
    print(json.dumps(store_export(json.loads(p.read_text(encoding="utf-8")), p.parent), indent=2))
