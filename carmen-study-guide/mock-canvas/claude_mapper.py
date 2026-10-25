"""
Ask Claude which learning outcomes one question assesses, and how much (the "Analyze goals" button on
each question, exam part and assignment).

Claude reads the course's syllabus outcomes and every released course material in Supabase (textbook,
lecture slides, syllabus; never student work or answer keys), plus the question and its assessment, and
returns a share per outcome with a reason and the material it relied on. The shares become
question_outcomes rows:

  provenance 'ai', weight = share (0-1, summing to 1), confidence = Claude's own estimate,
  rationale 'claude_v1 (<model>): ...', needs_review = true.

Only machine-proposed rows for that question are replaced (this mapper's or chapter_rule's). Instructor-
stated or reviewed mappings are never touched, and the chapter rule never overwrites Claude's rows.
LERs are rebuilt afterwards so the analytics see the new weights.

Needs ANTHROPIC_API_KEY in mock-canvas/.env.

    .venv/bin/python claude_mapper.py "VIBE 101" 2201 "FRQ 1 (a)"
"""

import json
import os
import sys

import anthropic

import ler_builder
from supabase_client import select_all, service_client

MODEL = "claude-opus-5-5"
RULE = "claude_v1"
MACHINE_RULES = ("chapter_rule", RULE)  # machine-proposed rationales this mapper may replace

INSTRUCTIONS = """You map assessment questions in a university course to the course's learning outcomes.

For the question you are given, decide which of the course's learning outcomes it actually assesses, and how
much of the question's credit reflects each one. Use the course materials below to see what each outcome
covers in this course and where the question's content is taught.

Rules:
- Only use outcome codes from the list below.
- Give each outcome you choose a share from 1 to 100; the shares must add up to 100. Choose the fewest
  outcomes that honestly describe the question (often one or two). Do not spread credit to an outcome the
  question only touches in passing.
- For a question that is a whole assessment or a multi-question section, weight the outcomes by how much of
  that assessment's credit addresses each one.
- reason: one or two plain sentences on why this outcome, citing the specific skill the question requires.
- sources: titles of the course materials below that teach the relevant content (up to three).
- confidence: 0 to 1, how sure you are of the overall mapping."""

SCHEMA = {
    "type": "object",
    "properties": {
        "outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "outcome_code": {"type": "string"},
                    "share": {"type": "integer"},
                    "reason": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["outcome_code", "share", "reason", "sources"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number"},
    },
    "required": ["outcomes", "confidence"],
    "additionalProperties": False,
}


class MappingError(Exception):
    """A problem the page should show the user (missing key, unknown question, unusable answer)."""


def _machine(row: dict) -> bool:
    return row["provenance"] == "ai" and row["needs_review"] and (row["rationale"] or "").startswith(MACHINE_RULES)


def _course_context(db, cid: str) -> tuple[str, dict[str, dict]]:
    """The stable part of the prompt: outcomes and all released course material (cached between clicks)."""
    outcomes = {o["code"]: o for o in select_all(db, "outcomes", "id,code,syllabus_text", course_id=cid)}
    chunks = [c for c in select_all(db, "resource_chunks", "title,content,doc_type,section,page,student_visible",
                                    course_id=cid) if c["student_visible"]]
    chunks.sort(key=lambda c: (c["doc_type"], c["title"] or "", c["page"] or 0, c["section"] or ""))
    lines = ["<outcomes>"] + [f"{code}: {o['syllabus_text']}" for code, o in sorted(outcomes.items())] + ["</outcomes>",
                                                                                                          "<course_materials>"]
    for c in chunks:
        where = " / ".join(str(x) for x in (c["title"], c["section"]) if x)
        lines.append(f'<material type="{c["doc_type"]}" title="{where}">\n{c["content"]}\n</material>')
    lines.append("</course_materials>")
    return "\n".join(lines), outcomes


def _question_prompt(assessment: dict, question: dict, whole_text: str) -> str:
    choices = [ch.get("text") for ch in (question.get("locator") or {}).get("choices", []) if ch.get("text")]
    parts = [f"Assessment: {assessment['title']} ({assessment['assessment_type']})"]
    if whole_text:
        parts.append(f"<assessment_description>\n{whole_text}\n</assessment_description>")
    label = "the whole assessment" if question["code"] == "WHOLE" else question["code"]
    parts.append(f"Question to map: {label} ({question['points_possible']} pts)")
    if question["code"] != "WHOLE":
        parts.append(f"<question>\n{question['text'] or question['code']}\n</question>")
    if choices:
        parts.append("Answer choices:\n" + "\n".join(f"- {c}" for c in choices))
    return "\n\n".join(parts)


def _ask_claude(system: str, prompt: str) -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MappingError("Add ANTHROPIC_API_KEY to mock-canvas/.env, then restart the server.")
    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if a safety classifier declines, the API retries on a fallback model
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            system=[{"type": "text", "text": INSTRUCTIONS},
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise MappingError("Claude rejected the API key in mock-canvas/.env (ANTHROPIC_API_KEY).")
    except anthropic.RateLimitError:
        raise MappingError("Claude is rate limiting requests. Wait a minute and try again.")
    except anthropic.APIStatusError as e:
        raise MappingError(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise MappingError("Could not reach the Claude API. Check the internet connection.")
    if response.stop_reason == "refusal":
        raise MappingError("Claude declined to map this question.")
    if response.stop_reason == "max_tokens":
        raise MappingError("Claude's answer was cut off. Try again.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return {"answer": json.loads(text), "model": response.model,
            "usage": {"input": response.usage.input_tokens, "output": response.usage.output_tokens,
                      "cache_read": response.usage.cache_read_input_tokens or 0}}


def map_question(course_code: str, assessment_canvas_id: str, code: str) -> dict:
    db = service_client()
    found = db.table("courses").select("id").eq("code", course_code).execute().data
    if not found:
        raise MappingError(f"{course_code} is not in the database yet. Open a course page to sync it.")
    cid = found[0]["id"]
    assessment = next(iter(db.table("assessments").select("id,title,assessment_type").eq("course_id", cid)
                           .eq("canvas_id", str(assessment_canvas_id)).execute().data), None)
    if not assessment:
        raise MappingError("This assessment is not in the database yet. Wait for the sync to finish.")
    questions = {q["code"]: q for q in db.table("questions").select("id,code,text,points_possible,locator")
                 .eq("assessment_id", assessment["id"]).execute().data}
    question = questions.get(code)
    if not question:
        raise MappingError(f"{code} is not in the database yet. Wait for the sync to finish.")

    existing = db.table("question_outcomes").select("outcome_id,weight,provenance,needs_review,rationale") \
        .eq("question_id", question["id"]).execute().data
    context, outcomes = _course_context(db, cid)
    code_of = {o["id"]: c for c, o in outcomes.items()}
    kept = [r for r in existing if not _machine(r)]
    if kept:  # instructor-stated or reviewed: leave them as they are (shown as shares, as the analytics use them)
        total = sum(r["weight"] for r in kept) or 1
        return {"status": "kept", "question": code, "message": "Set by the instructor or already reviewed; not changed.",
                "mappings": [{"outcome": code_of.get(r["outcome_id"]), "weight": round(r["weight"] / total, 4),
                              "text": outcomes.get(code_of.get(r["outcome_id"]), {}).get("syllabus_text"),
                              "reason": r["rationale"]} for r in kept]}

    whole = questions.get("WHOLE", {}).get("text") or ""
    reply = _ask_claude(context, _question_prompt(assessment, question, whole))
    picks = [p for p in reply["answer"]["outcomes"] if p["outcome_code"] in outcomes and p["share"] > 0]
    total = sum(p["share"] for p in picks)
    if not total:
        raise MappingError("Claude did not name any of this course's outcomes. Try again.")
    confidence = max(0.0, min(1.0, float(reply["answer"]["confidence"])))
    rows = [{"question_id": question["id"], "outcome_id": outcomes[p["outcome_code"]]["id"],
             "weight": round(p["share"] / total, 4), "provenance": "ai", "confidence": round(confidence, 3),
             "needs_review": True,
             "rationale": f"{RULE} ({reply['model']}): {p['reason']} Sources: {'; '.join(p['sources']) or 'none cited'}"}
            for p in picks]

    db.table("question_outcomes").delete().eq("question_id", question["id"]).eq("provenance", "ai") \
        .eq("needs_review", True).execute()  # only machine rows reach this point
    db.table("question_outcomes").upsert(rows, on_conflict="question_id,outcome_id").execute()
    lers = ler_builder.run(course_code)
    return {"status": "mapped", "question": code, "model": reply["model"], "confidence": confidence,
            "usage": reply["usage"], "lers": lers,
            "mappings": sorted(({"outcome": p["outcome_code"], "text": outcomes[p["outcome_code"]]["syllabus_text"],
                                 "weight": round(p["share"] / total, 4), "reason": p["reason"], "sources": p["sources"]}
                                for p in picks), key=lambda m: -m["weight"])}


if __name__ == "__main__":
    print(json.dumps(map_question(*sys.argv[1:4]), indent=2, default=str))
