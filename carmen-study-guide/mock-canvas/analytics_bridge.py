"""
Load current LERs from Supabase as the joined "envelopes" Richard's analytics adapter expects
(apps/api/app/analytics/ler_adapter.py), and optionally run his full pipeline as a check:

    .venv/bin/python analytics_bridge.py "VIBE 101"          # adapt -> features -> statistics, print a summary

Only whitelisted ids, scores, types and timestamps go into an envelope; no answer text, names or LER payload.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from supabase_client import select_all, service_client

ANALYTICS = Path(__file__).resolve().parents[2] / "apps" / "api"


def load_envelopes(course_code: str) -> list[dict]:
    db = service_client()
    cid = db.table("courses").select("id").eq("code", course_code).execute().data[0]["id"]
    lers = [l for l in select_all(db, "lers", "id,schema_version,course_id,learner_id,assessment_id,question_id,"
                                  "attempt_id,response_id,practice_attempt_id,revision,is_current,assessment_origin,"
                                  "assistance_level,hints_used,independent_correctness,analysis_status",
                                  course_id=cid) if l["is_current"]]
    responses = {r["id"]: r for r in select_all(db, "responses", "id,course_id,learner_id,question_id,attempt_id,"
                                                "points_earned", course_id=cid)}
    questions = {q["id"]: q for q in select_all(db, "questions", "id,course_id,assessment_id,points_possible,"
                                                "question_type", course_id=cid)}
    attempts = {a["id"]: a for a in select_all(db, "attempts", "id,course_id,assessment_id,learner_id,"
                                               "attempt_number,submitted_at", course_id=cid)}
    assessments = {a["id"]: a for a in select_all(db, "assessments", "id,course_id,assessment_type", course_id=cid)}
    mappings: dict[str, list] = {}
    for m in select_all(db, "question_outcomes", "question_id,outcome_id,weight,provenance,needs_review"):
        mappings.setdefault(m["question_id"], []).append(
            {"outcome_id": m["outcome_id"], "weight": str(m["weight"]), "provenance": m["provenance"],
             "needs_review": m["needs_review"]})
    evidence: dict[str, list] = {}
    for e in select_all(db, "ler_evidence", "ler_id,evidence_ref_id"):
        evidence.setdefault(e["ler_id"], []).append(e["evidence_ref_id"])

    return [{
        "ler": l,
        "response": responses.get(l["response_id"], {}),
        "question": questions.get(l["question_id"], {}),
        "attempt": attempts.get(l["attempt_id"], {}),
        "assessment": assessments.get(l["assessment_id"], {}),
        "outcome_mappings": mappings.get(l["question_id"], []),
        "errors": [],
        "errors_analyzed": False,  # no error taxonomy/classifier yet: "not classified", not "no errors"
        "evidence_ref_ids": sorted(set(evidence.get(l["id"], []))),
    } for l in lers]


def check(course_code: str) -> dict:
    """Run Richard's adapter, feature engineering and statistics on the real data."""
    sys.path.insert(0, str(ANALYTICS))
    from app.analytics.features import build_features
    from app.analytics.ler_adapter import adapt_ler
    from app.analytics.statistics import analyze_statistics

    envelopes = load_envelopes(course_code)
    results = [adapt_ler(e) for e in envelopes]
    records = [r.record for r in results if r.record is not None]
    issues = Counter(f"{i.field}:{i.code}" for r in results for i in r.issues)
    features = build_features(records)
    stats = analyze_statistics(records)
    sized = lambda xs: [s for s in xs if getattr(s, "observed_score_ratio", None) is not None]
    return {
        "envelopes": len(envelopes), "adapted": len(records), "quarantined": len(envelopes) - len(records),
        "adapter_issues": dict(issues),
        "feature_rows": {name: len(getattr(features, name)) for name in
                         ("observations", "outcomes", "errors", "practice", "exclusions")},
        "exclusion_reasons": dict(Counter(features.exclusions["reason"])) if len(features.exclusions) else {},
        "student_outcomes": len(stats.student_outcomes),
        "student_outcomes_with_ratio": len(sized(stats.student_outcomes)),
        "class_outcomes": len(stats.class_outcomes),
        "assessment_questions": len(stats.assessment_questions),
    }, stats


if __name__ == "__main__":
    summary, _ = check(sys.argv[1] if len(sys.argv) > 1 else "VIBE 101")
    print(json.dumps(summary, indent=2, default=str))
