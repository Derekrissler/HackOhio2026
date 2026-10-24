from fastapi import FastAPI
from fastapi.testclient import TestClient

from tutor.router import create_router
from tutor.service import TutorService
from tutor.tests.fakes import ME, OTHER, FakeLLM, FakeRepo, good


def make(learner=ME, llm=None, repo=None, limit=20):
    repo = repo or FakeRepo()
    service = TutorService(repo, llm or FakeLLM(*[good() for _ in range(10)]))
    who = {"who": learner}
    app = FastAPI()
    app.include_router(create_router(lambda request, course_id: who["who"], lambda: (service, repo),
                                     turns_per_minute=limit))
    return TestClient(app), repo, who


def test_turn_returns_reply_with_citation_links_and_no_internals():
    client, _, _ = make()
    body = client.post("/courses/1001/tutor/turn", json={"message": "what is a spec?"}).json()
    assert body["move"] == "ask" and body["session_id"]
    assert body["citations"][0] == {"id": "c1", "title": "Lecture 4: Python gotchas", "location": "slide 5",
                                    "deep_link": "/courses/1001/files/40#page=5"}
    assert "violations" not in body and "policy_decision" not in body


def test_unknown_learner_gets_404():
    client, _, _ = make(learner=None)
    assert client.post("/courses/1001/tutor/turn", json={"message": "hi"}).status_code == 404


def test_message_is_validated():
    client, _, _ = make()
    assert client.post("/courses/1001/tutor/turn", json={"message": ""}).status_code == 422
    assert client.post("/courses/1001/tutor/turn", json={"message": "x" * 4001}).status_code == 422


def test_other_students_session_is_404_for_turns_and_history():
    client, repo, who = make(learner=OTHER)
    sid = client.post("/courses/1001/tutor/turn", json={"message": "hi"}).json()["session_id"]
    who["who"] = ME
    assert client.post("/courses/1001/tutor/turn", json={"message": "hi", "session_id": sid}).status_code == 404
    assert client.get(f"/courses/1001/tutor/sessions/{sid}").status_code == 404


def test_history_returns_own_turns():
    client, _, _ = make()
    sid = client.post("/courses/1001/tutor/turn", json={"message": "hi"}).json()["session_id"]
    turns = client.get(f"/courses/1001/tutor/sessions/{sid}").json()["turns"]
    assert [t["speaker"] for t in turns] == ["student", "tutor"]


def test_malformed_ids_are_rejected_before_reaching_the_database():
    client, _, _ = make()
    assert client.post("/courses/1001/tutor/turn", json={"message": "hi", "session_id": "abc"}).status_code == 422
    assert client.post("/courses/1001/tutor/turn", json={"message": "hi", "outcome_id": "x"}).status_code == 422
    assert client.get("/courses/1001/tutor/sessions/abc").status_code == 404


def test_backend_failure_is_503():
    app = FastAPI()

    def broken():
        raise ConnectionError("supabase unreachable")

    app.include_router(create_router(lambda r, c: ME, broken))
    assert TestClient(app).post("/courses/1001/tutor/turn", json={"message": "hi"}).status_code == 503


def test_rate_limit_per_learner():
    client, _, _ = make(limit=2)
    codes = [client.post("/courses/1001/tutor/turn", json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_missing_configuration_is_503_not_a_crash():
    app = FastAPI()

    def unconfigured():
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    app.include_router(create_router(lambda r, c: ME, unconfigured))
    assert TestClient(app).post("/courses/1001/tutor/turn", json={"message": "hi"}).status_code == 503
