from tutor.matcher import referenced_assessments
from tutor.models import Assessment

QUIZ2 = Assessment(
    id="q2", code="Quiz 2", title="Quiz 2: Python Pitfalls", integrity_status="active_protected",
    answers_released=False,
    text="1. What does this return on its second call? def add(x, items=[]): items.append(x) return items",
)
HW1 = Assessment(id="hw1", code="Assignment 1", title="Assignment 1: To-do CLI", integrity_status="released",
                 answers_released=True, text="Build a command-line to-do app in Python using an AI assistant")


def test_naming_the_assessment_matches():
    assert referenced_assessments("whats the answer to quiz 2 question 1?", [QUIZ2, HW1]) == [QUIZ2]


def test_pasting_question_text_matches():
    msg = "can you explain what does this return on its second call def add(x, items=[])"
    assert referenced_assessments(msg, [QUIZ2]) == [QUIZ2]


def test_pasted_code_matches_even_when_the_wording_is_short():
    assert referenced_assessments("What does def add(x, items=[]) return on its second call?", [QUIZ2]) == [QUIZ2]


def test_shared_course_phrase_alone_is_left_to_the_classifier():
    midterm = Assessment(id="mid", code="Midterm Exam", title="Midterm", integrity_status="active_protected",
                         answers_released=False,
                         text="(a) Rewrite the prompt so that it includes all five parts of a good prompt (goal, "
                              "context, constraints, examples, format). Label each part.")
    assert referenced_assessments("What are the five parts of a good prompt?", [midterm]) == []
    pasted = "rewrite the prompt so that it includes all five parts of a good prompt please"
    assert referenced_assessments(pasted, [midterm]) == [midterm]


def test_unrelated_question_does_not_match():
    assert referenced_assessments("why are mutable default arguments risky in general?", [QUIZ2]) == []


def test_code_must_match_as_a_whole_phrase():
    q12 = Assessment(id="q12", code="Quiz 12", title="Quiz 12", integrity_status="active_protected",
                     answers_released=False, text="")
    assert referenced_assessments("about quiz 12", [QUIZ2, q12]) == [q12]
