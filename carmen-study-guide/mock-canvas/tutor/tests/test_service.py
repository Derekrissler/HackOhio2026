import pytest

from tutor.models import Mode
from tutor.service import NotFound, TurnRequest, TutorService
from tutor.tests.fakes import ME, OTHER, FakeLLM, FakeRepo, INJECTED, SLIDE, good

LEAK = "The default list is created once and shared between calls."


def run(llm, repo=None, learner=ME, **req):
    repo = repo or FakeRepo()
    result = TutorService(repo, llm).turn(learner, TurnRequest(**{"message": "help me", **req}))
    return result, repo


def system_notes(llm, i=-1) -> str:
    return " ".join(m["content"] for m in llm.requests[i]["messages"] if m["role"] == "system")


def test_naming_an_open_quiz_switches_to_protected_mode_and_says_so_to_the_model():
    llm = FakeLLM(good(move="explanation"))
    result, repo = run(llm, message="what's the answer to quiz 2 question 1?")
    assert result.mode is Mode.PROTECTED
    assert "protected assessment" in system_notes(llm)
    logged = repo.turns[result.session_id]
    assert [t["speaker"] for t in logged] == ["student", "tutor"]
    assert logged[1]["policy_decision"]["mode"] == "protected_assessment"


def test_paraphrased_reference_caught_by_classifier_is_protected():
    llm = FakeLLM(good(), references=["Quiz 2"])
    result, _ = run(llm, message="that question about appending to a list twice, what prints?")
    assert result.mode is Mode.PROTECTED


def test_reply_leaking_the_key_is_retried_with_the_violation_then_shown():
    llm = FakeLLM(good(message=LEAK, move="hint", hint_level=1), good(move="hint", hint_level=1))
    result, _ = run(llm, assessment_id="hw2", message="I'm stuck")
    assert result.mode is Mode.GUIDED
    assert len(llm.requests) == 2
    assert "answer key" in system_notes(llm)
    assert result.reply.message != LEAK and not result.fallback


def test_model_detected_paraphrase_leak_triggers_retry():
    llm = FakeLLM(good(), good(message="Think about when defaults are evaluated."), leaks=[True, False])
    result, _ = run(llm, assessment_id="hw2")
    assert len(llm.requests) == 2 and not result.fallback


def test_two_bad_replies_fall_back_to_a_safe_rule_based_reply():
    llm = FakeLLM(good(message=LEAK), good(message=LEAK), references=["Quiz 2"])
    result, repo = run(llm, assessment_id="hw2")
    assert result.fallback
    assert LEAK.lower() not in result.reply.message.lower()
    assert result.reply.cited_chunk_ids == ["c1"]
    assert repo.turns[result.session_id][1]["policy_decision"]["fallback"] is True


def test_model_outage_falls_back_instead_of_erroring():
    result, _ = run(FakeLLM(RuntimeError("api down")), message="what's on quiz 2?")
    assert result.fallback and result.reply.move == "decline"


def test_cannot_continue_another_students_session():
    llm = FakeLLM(good(), good())
    first, repo = run(llm, learner=OTHER)
    with pytest.raises(NotFound):
        run(llm, repo=repo, learner=ME, session_id=first.session_id)


def test_assessment_from_another_course_is_not_found():
    with pytest.raises(NotFound):
        run(FakeLLM(good()), assessment_id="not-in-my-course")


def test_hint_level_continues_from_the_session_history():
    llm = FakeLLM(good(move="hint", hint_level=1, cited_chunk_ids=["c1"]),
                  good(move="hint", hint_level=3, cited_chunk_ids=["c1"]),
                  good(move="hint", hint_level=2, cited_chunk_ids=["c1"]))
    first, repo = run(llm, assessment_id="hw2")
    second, _ = run(llm, repo=repo, session_id=first.session_id, assessment_id="hw2")
    assert len(llm.requests) == 3  # the jump from 1 to 3 was rejected and retried
    assert second.reply.hint_level == 2


def test_retrieval_is_course_scoped_and_boosts_weak_and_requested_outcomes():
    repo = FakeRepo(weak=["lo-weak"])
    run(FakeLLM(good()), repo=repo, outcome_id="lo-asked")
    assert repo.searches[0]["course_id"] == ME.course_id
    assert set(repo.searches[0]["outcome_ids"]) == {"lo-weak", "lo-asked"}


def test_course_material_is_fenced_as_data_and_cannot_close_its_own_tag():
    llm = FakeLLM(good())
    run(llm, repo=FakeRepo(chunks=[SLIDE, INJECTED]))
    user_turn = next(m for m in llm.requests[0]["messages"] if m["role"] == "user")["content"]
    assert user_turn.count("</course_material>") == 2  # only the real closing tags
    assert "untrusted" in llm.requests[0]["system"].lower()


def test_outcome_from_another_course_is_not_found():
    with pytest.raises(NotFound):
        run(FakeLLM(good()), outcome_id="someone-elses-outcome")


def test_staff_skip_the_reference_classifier():
    from dataclasses import replace
    llm = FakeLLM(good(move="explanation"))
    result, _ = run(llm, learner=replace(ME, role="instructor"), message="explain quiz-style questions")
    assert result.mode is Mode.STUDY and llm.reference_calls == 0


def test_session_records_the_strictest_mode_it_reached():
    llm = FakeLLM(good(move="explanation"), good(move="explanation"))
    first, repo = run(llm, message="what is a spec?")
    assert repo.session_modes[first.session_id] == "independent_study"
    run(llm, repo=repo, session_id=first.session_id, message="and what's the answer to quiz 2 question 1?")
    assert repo.session_modes[first.session_id] == "protected_assessment"


def test_classifier_is_told_which_assessment_the_student_is_working_on():
    llm = FakeLLM(good(move="explanation"))
    run(llm, assessment_id="quiz1", message="explain the answer to question 1")
    assert llm.reference_current == "quiz1"


def test_released_assessment_text_and_key_are_given_to_the_tutor_as_citable_material():
    repo = FakeRepo(answers={"quiz1": ["1. B: a fast prototype loop"]})
    llm = FakeLLM(good(move="explanation", cited_chunk_ids=["assessment-quiz1"]))
    result, _ = run(llm, repo=repo, assessment_id="quiz1", message="explain question 1")
    user_turn = next(m for m in llm.requests[0]["messages"] if m["role"] == "user")["content"]
    assert 'id="assessment-quiz1"' in user_turn and "a fast prototype loop" in user_turn
    assert not result.fallback and result.citations[0].id == "assessment-quiz1"


def test_open_assessment_text_and_key_never_reach_the_tutor():
    llm = FakeLLM(good(move="explanation"))
    run(llm, assessment_id="hw2", message="help with this")
    run(llm, message="what's the answer to quiz 2 question 1?")
    for request in llm.requests:
        sent = " ".join(m["content"] for m in request["messages"])
        assert "created once and shared" not in sent and "assessment-" not in sent


def test_tutor_is_told_what_the_student_is_working_on():
    llm = FakeLLM(good(move="hint", hint_level=1))
    run(llm, assessment_id="hw2", message="help")
    assert "Assignment 2: Test first" in system_notes(llm)


def test_released_assessment_allows_independent_study():
    llm = FakeLLM(good(move="explanation"))
    result, _ = run(llm, assessment_id="quiz1", message="walk me through quiz 1 question 3")
    assert result.mode is Mode.STUDY and not result.fallback


def test_leak_check_runs_even_in_independent_study_as_the_backstop():
    # The classifier can miss a paraphrased quiz question; the leak check must still catch the answer.
    llm = FakeLLM(good(move="explanation"), good(message="Trace it by hand first."), leaks=[True, False])
    result, _ = run(llm, message="what happens with mutable default arguments?")
    assert result.mode is Mode.STUDY
    assert llm.leak_checks == 2 and "paraphrases the answer key" in " ".join(result.violations)
