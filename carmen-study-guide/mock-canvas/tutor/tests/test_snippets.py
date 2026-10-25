from tutor.models import Chunk, Mode, Snippet
from tutor.snippets import MAX_SNIPPETS, select_snippets
from tutor.tests.fakes import good
from tutor.verifier import check_reply

SLIDE = Chunk(id="s3", title="Lecture 1 slides: What Is Vibe Coding?", doc_type="slides", page=3, slide=3,
              deep_link="/courses/1001/files/301#page=3",
              content="Definition\nVibe coding: building software by describing intent in natural language and\n"
                      "having an AI generate most of the code.\nYour job changes from typing to directing, reviewing, "
                      "verifying.")
AGENDA = Chunk(id="s2", title="Lecture 1 slides", doc_type="slides", page=2, slide=2, deep_link=None,
               content="Today’s Agenda\n- Define vibe coding\n- Where it shines, where it burns")


def pick(*snips, chunks=(SLIDE, AGENDA)):
    return select_snippets([Snippet(chunk_id=c, quote=q) for c, q in snips], {c.id: c for c in chunks})


def test_verbatim_quote_is_kept_and_shown_with_the_slides_own_line_breaks():
    kept, dropped = pick(("s3", "building software by describing intent in natural language and having an AI "
                                "generate most of the code."))
    assert dropped == []
    assert kept[0].chunk is SLIDE
    assert kept[0].text == ("building software by describing intent in natural language and\nhaving an AI generate "
                            "most of the code.")


def test_quote_style_and_spacing_differences_still_match():
    kept, _ = pick(("s2", "Today's Agenda  - Define vibe coding"))
    assert kept[0].text == "Today’s Agenda\n- Define vibe coding"


def test_invented_or_altered_quote_is_dropped():
    kept, dropped = pick(("s3", "Vibe coding means the AI writes all of the code."))
    assert kept == [] and "not found" in dropped[0]


def test_quote_from_material_that_was_not_retrieved_is_dropped():
    kept, dropped = pick(("s99", "Definition"))
    assert kept == [] and "not retrieved" in dropped[0]


def test_at_most_a_few_short_snippets_and_no_duplicates():
    many = [("s3", "Definition"), ("s3", "Definition"), ("s2", "Define vibe coding"),
            ("s2", "Where it shines"), ("s3", "verifying.")]
    kept, _ = pick(*many)
    assert len(kept) == MAX_SNIPPETS and len({k.text for k in kept}) == len(kept)
    long_quote = SLIDE.content * 3
    assert pick(("s3", long_quote))[0] == []


def test_snippet_text_counts_for_the_answer_key_leak_check():
    r = good(snippets=[Snippet(chunk_id="c1", quote="the default list is created once and shared between calls")])
    violations = check_reply(r, mode=Mode.PROTECTED, retrieved_ids={"c1"}, prev_hint=0,
                             answer_texts=["The default list is created once and shared between calls"],
                             own_pseudonym="S-aaaaaaaaaa")
    assert any("answer key" in v for v in violations)
