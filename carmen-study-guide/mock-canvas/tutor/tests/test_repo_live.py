"""Runs against the shared Supabase project when a service key is set; skipped otherwise.

Writes one tutor session for the VIBE 101 learner and deletes it afterwards.
"""

import os

import pytest

from tutor.models import Mode

pytestmark = pytest.mark.skipif(
    not os.environ.get("TUTOR_TEST_ACCESS_TOKEN") or not any(os.environ.get(k, "") not in ("", "REPLACE_ME", "YOUR-SECRET-KEY") for k in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY")),
    reason="explicit live-test user token and service key required",
)


@pytest.fixture(scope="module")
def repo():
    from supabase_client import service_client, user_client
    from tutor.models import Learner
    from tutor.repo import SupabaseTutorRepo

    reader = user_client(os.environ["TUTOR_TEST_ACCESS_TOKEN"])
    uid = reader.auth.get_user(os.environ["TUTOR_TEST_ACCESS_TOKEN"]).user.id
    mapping = reader.table("learner_identities").select("learner_id,course_id").eq("user_id", str(uid)).limit(1).execute().data[0]
    person = reader.table("learners").select("pseudonym").eq("id", mapping["learner_id"]).execute().data[0]
    return SupabaseTutorRepo(service_client(), reader, Learner(mapping["course_id"], mapping["learner_id"], person["pseudonym"]))


@pytest.fixture(scope="module")
def learner(repo):
    return repo.identity


def test_unknown_learner_or_course_is_none(repo, learner):
    assert repo.learner("no-such-course", learner.pseudonym) is None


def test_assessments_carry_policy_and_question_text(repo, learner):
    assessments = repo.assessments(learner.course_id)
    assert assessments and all(a.integrity_status for a in assessments)
    assert any(a.text for a in assessments)


def test_search_returns_only_student_visible_course_chunks(repo, learner):
    chunks = repo.search(learner.course_id, "prompt specification", [], 5)
    assert chunks
    ids = [c.id for c in chunks]
    rows = repo.db.table("resource_chunks").select("course_id,student_visible,publication_status").in_("id", ids).execute().data
    assert all(r["course_id"] == learner.course_id and r["student_visible"] and r["publication_status"] == "released"
               for r in rows)


def test_search_handles_a_natural_question_not_just_keywords(repo, learner):
    chunks = repo.search(learner.course_id, "What makes a good prompt specification?", [], 5)
    assert chunks, "a full question must still find material (terms are ORed, not ANDed)"
    assert any("specification" in c.title.lower() or "spec" in c.content.lower() for c in chunks)


def test_session_turns_round_trip_in_order(repo, learner):
    session = repo.create_session(learner, Mode.GUIDED, None, None)
    try:
        repo.add_turns(session.id, [{"speaker": "student", "content": "q"},
                                    {"speaker": "tutor", "content": "a", "pedagogical_move": "hint", "hint_level": 1,
                                     "cited_chunk_ids": [], "policy_decision": {"mode": "guided_homework"}}])
        assert repo.get_session(session.id).learner_id == learner.learner_id
        assert [(t.speaker, t.hint_level) for t in repo.history(session.id, 10)] == [("student", None), ("tutor", 1)]
    finally:
        repo.db.table("tutor_sessions").delete().eq("id", session.id).execute()
