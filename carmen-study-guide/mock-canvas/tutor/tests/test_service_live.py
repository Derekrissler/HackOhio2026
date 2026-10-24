"""Full turn against the shared Supabase project with a scripted model. Needs a service key and demo_setup applied.

Cleans up the tutor sessions it creates.
"""

import pytest

from tutor.models import Mode
from tutor.service import TurnRequest, TutorService
from tutor.tests.fakes import FakeLLM, good
from tutor.tests.test_repo_live import learner, pytestmark, repo  # noqa: F401  (fixtures + skip marker)


@pytest.fixture
def service_for(repo):
    created = []

    def make(llm):
        svc = TutorService(repo, llm)
        original = repo.create_session

        def tracking(*a, **kw):
            s = original(*a, **kw)
            created.append(s.id)
            return s

        repo.create_session = tracking
        return svc

    yield make
    repo.create_session = type(repo).create_session.__get__(repo)
    for sid in created:
        repo.db.table("tutor_sessions").delete().eq("id", sid).execute()


def test_leaking_draft_on_open_quiz_is_blocked_and_logged(repo, learner, service_for):
    leak = "It's C: a call to a function or library that does not exist."
    result = service_for(FakeLLM(good(message=leak, move="explanation", cited_chunk_ids=[]),
                                 good(message=leak, move="explanation", cited_chunk_ids=[]))) \
        .turn(learner, TurnRequest("what's the answer to quiz 2 question 2?"))
    assert result.mode is Mode.PROTECTED and result.fallback
    assert "does not exist" not in result.reply.message
    logged = repo.session_turns(result.session_id)
    assert [t["speaker"] for t in logged] == ["student", "tutor"]
    assert logged[1]["pedagogical_move"] == "decline"


def test_guided_homework_turn_cites_real_released_chunks(repo, learner, service_for):
    hw2 = next(a for a in repo.assessments(learner.course_id) if a.code == "Assignment 2")
    question = "how do I write tests first?"
    chunks = repo.search(learner.course_id, question, [], 6)  # the same search the turn will run
    assert chunks
    llm = FakeLLM(good(message="What should your first test check?", move="hint", hint_level=1,
                       cited_chunk_ids=[chunks[0].id]))
    result = service_for(llm).turn(learner, TurnRequest(question, assessment_id=hw2.id))
    assert result.mode is Mode.GUIDED and not result.fallback
    assert [c.id for c in result.citations] == [chunks[0].id]
