"""
Demo sign-in accounts for VIBE 101, so the tutor's Supabase sign-in and the instructor dashboard can be shown.
Safe to re-run: existing accounts are reused and links are upserted.

- student1@demo.test: the mock Canvas's signed-in student (S-991493db34, the most graded work)
- student2@demo.test: a second student, to show one student can't see another's data
- instructor@demo.test: instructor enrollment only. The dashboard needs nothing more, and no learner row is
  invented, so analytics populations stay real. (The tutor is for students and needs a learner link.)

All accounts use DEMO_ACCOUNT_PASSWORD from mock-canvas/.env (never commit it). Pseudonyms assume the default
ANON_SALT used by the export.

    .venv/Scripts/python -m tutor.demo_accounts            # show what would change
    .venv/Scripts/python -m tutor.demo_accounts --apply
"""

import os
import sys

COURSE_CANVAS_ID = "1001"
ACCOUNTS = [
    # email, display name, enrollment role, learner pseudonym (None: no learner link)
    ("student1@demo.test", "Demo Student 1", "student", "S-991493db34"),
    ("student2@demo.test", "Demo Student 2", "student", "S-2725856e98"),
    ("instructor@demo.test", "Demo Instructor", "instructor", None),
]


def _existing_users(db) -> dict[str, str]:
    users, page = {}, 1
    while True:
        batch = db.auth.admin.list_users(page=page, per_page=200)
        users.update({u.email.lower(): u.id for u in batch if u.email})
        if len(batch) < 200:
            return users
        page += 1


def main(apply: bool) -> None:
    from supabase_client import service_client

    password = os.environ.get("DEMO_ACCOUNT_PASSWORD", "")
    if len(password) < 8:
        sys.exit("Set DEMO_ACCOUNT_PASSWORD (8+ characters) in mock-canvas/.env first.")
    db = service_client()
    course = db.table("courses").select("id").eq("canvas_id", COURSE_CANVAS_ID).single().execute().data
    learners = {r["pseudonym"]: r["id"] for r in
                db.table("learners").select("id,pseudonym").eq("course_id", course["id"]).execute().data}
    users = _existing_users(db)

    for email, name, role, pseudonym in ACCOUNTS:
        if pseudonym and pseudonym not in learners:
            sys.exit(f"{email}: learner {pseudonym} isn't in VIBE 101. Export the course first.")
        uid = users.get(email)
        print(f"{email}: {'exists' if uid else 'create'}, enroll as {role}"
              + (f", link to {pseudonym}" if pseudonym else ""))
        if not apply:
            continue
        if uid:
            db.auth.admin.update_user_by_id(uid, {"password": password})
        else:
            uid = db.auth.admin.create_user({"email": email, "password": password, "email_confirm": True,
                                             "user_metadata": {"display_name": name}}).user.id
        db.table("profiles").upsert({"id": uid, "display_name": name}).execute()
        db.table("enrollments").upsert({"course_id": course["id"], "user_id": uid, "role": role}).execute()
        if pseudonym:
            db.table("learner_identities").upsert({"learner_id": learners[pseudonym], "user_id": uid,
                                                   "course_id": course["id"]}).execute()
    if not apply:
        print("Dry run. Re-run with --apply to write.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
