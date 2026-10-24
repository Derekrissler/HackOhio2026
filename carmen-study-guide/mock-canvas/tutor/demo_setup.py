"""
Instructor-side demo setup for VIBE 101, so every tutor mode can be shown. Safe to re-run.

- Quiz 2 stays protected and gets a (fictional) answer key, so the leak checks have something to protect.
- Assignment 2 becomes guided homework (hints, not answers).
- Quiz 1 is released with answers (independent study).

Answer keys never leave the server: question_answer_keys is staff-only under RLS and is never indexed for retrieval.

    .venv/Scripts/python -m tutor.demo_setup            # show what would change
    .venv/Scripts/python -m tutor.demo_setup --apply
"""

import sys

COURSE_CANVAS_ID = "1001"
POLICIES = {
    "Assignment 2": {"integrity_status": "guided_homework", "answers_released": False},
    "Quiz 1": {"integrity_status": "released", "answers_released": True},
    "Quiz 2": {"integrity_status": "active_protected", "answers_released": False},
}
QUIZ2_ANSWER = """\
1. A: [1, 2]
2. C: a call to a function or library that does not exist
3. D: check whether it matches the spec and trace it on a small example
4. C: it silently hides all errors, making failures hard to detect
5. D: an empty list
6. B: write the spec and tests first, then have the AI generate code to pass them
7. C: they may share the same blind spots as the code
8. C: a test added to ensure a previously fixed bug does not return"""
QUIZ2_SOLUTION = """\
1. The default list is created once when the function is defined and is shared between calls, so the second call returns [1, 2].
9. Any two items from the six-item reading checklist, with a correct one-sentence explanation of one of them.
10. Restore the test, read why it fails, and fix the code (or the spec, if the test is wrong); never delete a failing test to make it pass."""


def main(apply: bool) -> None:
    from supabase_client import service_client

    db = service_client()
    course = db.table("courses").select("id").eq("canvas_id", COURSE_CANVAS_ID).single().execute().data
    rows = db.table("assessments").select("id,code,integrity_status,answers_released") \
        .eq("course_id", course["id"]).in_("code", list(POLICIES)).execute().data
    by_code = {r["code"]: r for r in rows}

    for code, policy in POLICIES.items():
        row = by_code[code]
        change = {k: v for k, v in policy.items() if row[k] != v}
        print(f"{code}: {change or 'no change'}")
        if apply and change:
            db.table("assessments").update(change).eq("id", row["id"]).execute()

    whole = db.table("questions").select("id").eq("assessment_id", by_code["Quiz 2"]["id"]).eq("code", "WHOLE") \
        .single().execute().data
    print("Quiz 2 answer key: upsert")
    if apply:
        db.table("question_answer_keys").upsert({"question_id": whole["id"], "course_id": course["id"],
                                                 "answer": QUIZ2_ANSWER, "solution": QUIZ2_SOLUTION}).execute()
    if not apply:
        print("Dry run. Re-run with --apply to write.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
