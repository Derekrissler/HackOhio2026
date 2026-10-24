from tutor.models import Mode, TutorReply
from tutor.verifier import check_reply

RETRIEVED = {"c1", "c2"}
KEY = ["[1, 2]", "The default list is created once and shared between calls"]


def reply(**kw) -> TutorReply:
    base = dict(message="What do you think happens to the list between calls?", move="ask", hint_level=0,
                cited_chunk_ids=["c1"], next_step="Re-read slide 5.")
    return TutorReply(**{**base, **kw})


def check(r: TutorReply, mode=Mode.GUIDED, prev_hint=0, answers=KEY):
    return check_reply(r, mode=mode, retrieved_ids=RETRIEVED, prev_hint=prev_hint, answer_texts=answers,
                       own_pseudonym="S-aaaaaaaaaa")


def test_clean_reply_passes():
    assert check(reply()) == []


def test_answer_key_text_is_caught_even_with_different_spacing_and_case():
    r = reply(message="Hint: the DEFAULT list is created   once and shared between calls.", move="hint", hint_level=1)
    assert any("answer key" in v for v in check(r))


def test_numbered_key_lines_match_without_their_numbering_or_option_letter():
    key = ["1. A: [1, 2]\n2. C: a call to a function or library that does not exist"]
    r = reply(message="It's C: a call to a function or library that does not exist.")
    assert any("answer key" in v for v in check(r, mode=Mode.PROTECTED, answers=key))


def test_short_answer_fragments_are_left_to_the_model_checker():
    # Too short to match reliably; they must not flag every reply that mentions a list
    r = reply(message="Lists like [1, 2] are mutable; also test an empty list.")
    assert check(r, mode=Mode.STUDY, answers=["[1, 2]", "an empty list"]) == []


def test_citation_outside_retrieved_chunks_fails():
    assert any("citation" in v for v in check(reply(cited_chunk_ids=["c9"])))


def test_substantive_reply_without_citation_fails_when_material_exists():
    assert any("cite" in v for v in check(reply(move="hint", hint_level=1, cited_chunk_ids=[])))


def test_move_not_allowed_in_mode_fails():
    assert any("move" in v for v in check(reply(move="hint", hint_level=1), mode=Mode.PROTECTED))
    assert any("move" in v for v in check(reply(move="explanation"), mode=Mode.GUIDED))


def test_hint_level_cannot_jump():
    assert any("hint" in v for v in check(reply(move="hint", hint_level=3), prev_hint=1))
    assert check(reply(move="hint", hint_level=2), prev_hint=1) == []


def test_protected_mode_never_hints():
    assert any("hint" in v for v in check(reply(move="explanation", hint_level=1), mode=Mode.PROTECTED))


def test_other_students_pseudonym_is_a_privacy_violation():
    assert any("student" in v for v in check(reply(message="Unlike S-0123456789, you did fine.")))
    assert check(reply(message="Your id is S-aaaaaaaaaa.")) == []
