"""
Propose question -> outcome mappings for questions that have none (quiz items, exam parts).

Rule (chapter_rule_v2), deterministic and explainable:
  1. Candidate chapters = the assessment's chapter scope (from its title, description or module headings,
     e.g. "Quiz 1: Chapters 1-2", "Review: Chapters 1-4"), else all chapters.
  2. A multi-question section ("Part I: 12 multiple choice"), or an assessment-level score with no
     instructor-stated outcomes (e.g. a student's overall exam grade), maps to every chapter in scope.
  3. Otherwise score the question text against each candidate chapter's full textbook text (TF-IDF cosine),
     take the best chapter, plus the runner-up if it scores within 85% of the best.
  4. Map to those chapters' syllabus outcomes from mappings/<course>.json.
Written to question_outcomes with provenance 'ai' (machine-proposed), weight 1.0, the score as confidence,
the reasoning as rationale, and needs_review = true. Questions that already have any mapping
(instructor-stated, or reviewed) are never touched.

    .venv/bin/python outcome_mapper.py "VIBE 101"
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

from ingest import chapter_number, chapter_refs
from supabase_client import select_all, service_client

HERE = Path(__file__).resolve().parent
RULE = "chapter_rule_v2"
RUNNER_UP = 0.85
STOP = set("the a an and or of to in is it for on that this with as be are was you your not but if at by from have "
           "has i we they can will what which when how why does do one two each its into than then them these those "
           "code ai".split())


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z_]{2,}", (text or "").lower()) if w not in STOP]


def question_text(q: dict, whole_text: str) -> str:
    """Quiz items carry their own stem + choices; exam parts borrow their FRQ / Part text from the exam
    (the longest matching block, so a one-line mention in the exam's preface doesn't win)."""
    text = q["text"] or ""
    choices = " ".join(c.get("text", "") for c in (q.get("locator") or {}).get("choices", []))
    if q["question_type"] == "rubric_question_part" and whole_text:
        m = re.match(r"(FRQ\s*\d+|Part\s+[IVX]+)", q["code"])
        if m:
            label = re.escape(m.group(1)).replace(r"\ ", r"\s*")
            nxt = r"(?=FRQ\s*\d+\s*\(\d+\s*pts\)|Part\s+[IVX]+:|$)"
            blocks = [b.group(0) for b in re.finditer(label + r".*?" + nxt, whole_text, flags=re.S)]
            if blocks:
                text = f"{text}\n{max(blocks, key=len)}"
    return f"{text}\n{choices}"


def run(course_code: str) -> dict:
    db = service_client()
    mapping = json.loads((HERE / "mappings" / f"{re.sub(r'[^a-z0-9]+', '', course_code.lower())}.json").read_text())
    course = db.table("courses").select("id").eq("code", course_code).execute().data[0]
    cid = course["id"]
    outcomes = {o["code"]: o["id"] for o in select_all(db, "outcomes", "id,code", course_id=cid)}

    # Textbook chunks grouped by chapter -> TF-IDF vectors
    chunks = [c for c in select_all(db, "resource_chunks", "title,content,doc_type,student_visible", course_id=cid)
              if c["doc_type"] == "textbook" and chapter_number(c["title"] or "")]
    by_chapter: dict[int, Counter] = {}
    for c in chunks:
        by_chapter.setdefault(chapter_number(c["title"]), Counter()).update(tokens(c["content"]))
    df = Counter(w for d in by_chapter.values() for w in d)
    idf = {w: math.log((1 + len(by_chapter)) / (1 + n)) + 1 for w, n in df.items()}
    vec = lambda counts: {w: n * idf.get(w, 1.0) for w, n in counts.items()}
    chapter_vecs = {ch: vec(d) for ch, d in by_chapter.items()}

    def cos(a, b):
        num = sum(v * b.get(w, 0) for w, v in a.items())
        den = math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))
        return num / den if den else 0.0

    assessments = {a["id"]: a for a in select_all(db, "assessments", "id,title", course_id=cid)}
    questions = select_all(db, "questions", "id,assessment_id,code,text,question_type,locator", course_id=cid)
    whole = {q["assessment_id"]: q["text"] or "" for q in questions if q["code"] == "WHOLE"}
    existing = select_all(db, "question_outcomes", "question_id,provenance,needs_review,rationale")
    own = lambda r: r["provenance"] == "ai" and r["needs_review"] and (r["rationale"] or "").startswith("chapter_rule")
    protected = {r["question_id"] for r in existing if not own(r)}  # instructor-stated or reviewed: never touched
    all_chapters = sorted(chapter_vecs)
    scope = {q["assessment_id"]: (q.get("locator") or {}).get("chapters_covered") or []
             for q in questions if q["code"] == "WHOLE"}

    rows, skipped = [], []
    for q in questions:
        if q["id"] in protected:
            continue  # keep instructor-stated and reviewed mappings
        title = assessments[q["assessment_id"]]["title"]
        in_scope = scope.get(q["assessment_id"]) or chapter_refs(title)
        if q["code"] == "WHOLE" and not in_scope:
            continue  # an overall score with no stated outcomes and no chapter scope: leave unmapped
        candidates = [c for c in in_scope if c in all_chapters] or all_chapters
        qv = vec(Counter(tokens(question_text(q, whole.get(q["assessment_id"], "")))))
        scores = {ch: cos(qv, chapter_vecs[ch]) for ch in candidates}
        best = max(scores, key=scores.get)
        if q["code"] == "WHOLE":
            chosen, why = candidates, "assessment-level score: every chapter in scope"
        elif re.match(r"Part\s+[IVX]+\b", q["code"]) and in_scope:
            chosen, why = candidates, "multi-question section: every chapter in scope"
        elif scores[best] > 0:
            chosen = sorted((ch for ch in candidates if scores[ch] >= RUNNER_UP * scores[best]),
                            key=lambda ch: -scores[ch])[:2]
            why = "question text best matches " + " and ".join(f"Chapter {ch} ({scores[ch]:.2f})" for ch in chosen)
        else:
            skipped.append(q["code"])
            continue
        for ch in chosen:
            for code in mapping["chapter_outcomes"].get(str(ch), []):
                if code in outcomes:
                    rows.append({"question_id": q["id"], "outcome_id": outcomes[code], "weight": 1.0,
                                 "provenance": "ai", "confidence": round(scores[ch], 3), "needs_review": True,
                                 "rationale": f"{RULE}: {why}; chapters in scope {candidates} for '{title}'; "
                                              f"{mapping['rationale'][str(ch)]}"})
    # one row per (question, outcome): two chapters can share an outcome
    unique = {(r["question_id"], r["outcome_id"]): r for r in rows}
    # Replace this mapper's earlier proposals for the questions it just mapped, then write the new ones.
    redo = list({r["question_id"] for r in unique.values()})
    for i in range(0, len(redo), 100):
        db.table("question_outcomes").delete().in_("question_id", redo[i:i + 100]).eq("provenance", "ai") \
            .eq("needs_review", True).like("rationale", "chapter_rule%").execute()
    if unique:
        db.table("question_outcomes").upsert(list(unique.values()), on_conflict="question_id,outcome_id").execute()
    return {"rule": RULE, "questions_mapped": len({r["question_id"] for r in unique.values()}),
            "mappings_written": len(unique), "unmatched_questions": skipped}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "VIBE 101"), indent=2))
