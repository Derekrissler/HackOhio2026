"""
Build Learning Evidence Records (spec §6) from the stored Canvas facts: one current LER per graded response.

Deterministic (ler_builder_v1), no AI:
- One LER per response row (question-level for quizzes and exam parts; assignment-level otherwise).
  Quiz overall scores get no LER: they are the sum of the question LERs and would double-count.
- analysis_status = analyzed when the response has a score; insufficient (with a reason) when it has
  neither a score nor any feedback to analyze.
- assistance_level = 'independent': graded Canvas work, with no tutor hints recorded (spec §11.4).
- ler_outcomes copy the question's outcome mappings (provenance question_mapping).
- ler_evidence links the response's grader comments, rubric notes and OCR lines.
- No error classification yet (no agreed error taxonomy): ler_errors stays empty.

LERs are append-only. A new revision is inserted only when the response, its outcome mappings or its
evidence changed; the database trigger then supersedes the old LER and marks dependent ARRs stale.

    .venv/bin/python ler_builder.py "VIBE 101"
"""

import hashlib
import json
import sys

from supabase_client import select_all, service_client

BUILDER = "ler_builder_v1"
BATCH = 200


def _fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def run(course_code: str) -> dict:
    db = service_client()
    cid = db.table("courses").select("id").eq("code", course_code).execute().data[0]["id"]

    assessments = {a["id"]: a for a in select_all(db, "assessments", "id,assessment_type", course_id=cid)}
    questions = {q["id"]: q for q in select_all(db, "questions", "id,assessment_id,code,question_type", course_id=cid)}
    responses = select_all(db, "responses", "id,attempt_id,question_id,learner_id,points_earned,content_hash,locator",
                           course_id=cid)
    mappings: dict[str, list] = {}
    for m in select_all(db, "question_outcomes", "question_id,outcome_id,weight,provenance,confidence,needs_review"):
        if m["question_id"] in questions:
            mappings.setdefault(m["question_id"], []).append(m)

    # Evidence per response: feedback rows point at it; OCR lines belong to its submitted documents.
    evidence: dict[str, list[tuple[str, str]]] = {}
    for f in select_all(db, "feedback", "response_id,evidence_ref_id", course_id=cid):
        if f["evidence_ref_id"]:
            evidence.setdefault(f["response_id"], []).append((f["evidence_ref_id"], "feedback"))
    doc_by_attachment = {d["canvas_id"].split(":", 1)[1]: d["id"]
                         for d in select_all(db, "documents", "id,canvas_id,doc_type", course_id=cid)
                         if d["doc_type"] == "submission_scan" and (d["canvas_id"] or "").startswith("canvas_attachment:")}
    ocr_lines: dict[str, list[str]] = {}
    for e in select_all(db, "evidence_refs", "id,document_id,source_type", course_id=cid):
        if e["source_type"] in ("pdf", "image") and e["document_id"]:
            ocr_lines.setdefault(e["document_id"], []).append(e["id"])

    current = {l["response_id"]: l for l in select_all(db, "lers", "id,response_id,payload,is_current", course_id=cid)
               if l["is_current"] and l["response_id"]}
    attempts = {a["id"]: a for a in select_all(db, "attempts", "id,assessment_id", course_id=cid)}

    new_lers, links = [], []
    skipped_quiz_totals = unchanged = 0
    for r in responses:
        q = questions[r["question_id"]]
        a = assessments[q["assessment_id"]]
        if a["assessment_type"] == "quiz" and q["question_type"] == "assignment_level":
            skipped_quiz_totals += 1
            continue
        refs = list(evidence.get(r["id"], []))
        if q["question_type"] == "assignment_level":  # OCR lines of the files attached to this submission
            for att in (r.get("locator") or {}).get("attachments", []):
                doc = doc_by_attachment.get(str(att.get("canvas_file_id")))
                refs += [(e, "response") for e in ocr_lines.get(doc, [])]
        refs = sorted(set(refs))
        maps = sorted(mappings.get(q["id"], []), key=lambda m: m["outcome_id"])
        fp = _fingerprint(r["content_hash"], r["points_earned"], maps, refs)
        cur = current.get(r["id"])
        if cur and (cur["payload"] or {}).get("fingerprint") == fp:
            unchanged += 1
            continue
        has_feedback = any(role == "feedback" for _, role in refs)
        analyzed = r["points_earned"] is not None or has_feedback
        new_lers.append(({
            "course_id": cid, "learner_id": r["learner_id"], "assessment_id": q["assessment_id"],
            "question_id": q["id"], "attempt_id": r["attempt_id"], "response_id": r["id"],
            "assessment_origin": "graded_canvas", "assistance_level": "independent",
            "analysis_status": "analyzed" if analyzed else "insufficient",
            "insufficiency_reason": None if analyzed else "Not graded and no feedback: nothing to analyze yet.",
            "extraction_version": BUILDER,
            "payload": {"builder": BUILDER, "fingerprint": fp, "question_code": q["code"],
                        "question_type": q["question_type"], "evidence_count": len(refs),
                        "outcome_count": len(maps)},
        }, maps, refs))

    created = []
    for i in range(0, len(new_lers), BATCH):
        batch = new_lers[i:i + BATCH]
        created += db.table("lers").insert([row for row, _, _ in batch]).execute().data
    ler_outcomes, ler_evidence = [], []
    for row, (_, maps, refs) in zip(created, new_lers):
        ler_outcomes += [{"ler_id": row["id"], "outcome_id": m["outcome_id"], "confidence": m["confidence"],
                          "provenance": "question_mapping", "needs_review": m["needs_review"]} for m in maps]
        ler_evidence += [{"ler_id": row["id"], "evidence_ref_id": e, "role": role} for e, role in refs]
    for table, rows in (("ler_outcomes", ler_outcomes), ("ler_evidence", ler_evidence)):
        for i in range(0, len(rows), 500):
            db.table(table).insert(rows[i:i + 500]).execute()
    return {"builder": BUILDER, "lers_created": len(created), "unchanged": unchanged,
            "quiz_totals_skipped": skipped_quiz_totals, "ler_outcomes": len(ler_outcomes),
            "ler_evidence": len(ler_evidence)}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "VIBE 101"), indent=2))
