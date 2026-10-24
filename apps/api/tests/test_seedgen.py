import json
import re
import zlib

import pytest

from seedgen.build import build
from seedgen.content import ISE


@pytest.fixture(scope="module")
def seed() -> dict[str, bytes]:
    return build()


def _content_streams(pdf: bytes) -> list[bytes]:
    """Decoded non-image streams. Image bytes can contain 'BT'/'ET' by chance, so skip them."""
    out = []
    for header, raw in re.findall(rb"<<((?:(?!>>\s*stream).)*?)>>\s*stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        if b"/Subtype /Image" in header:
            continue
        try:
            out.append(zlib.decompress(raw))
        except zlib.error:
            out.append(raw)
    return out


def _has_text(pdf: bytes) -> bool:
    return any(re.search(rb"\bBT\b.*?\bET\b", s, re.S) for s in _content_streams(pdf))


def test_generator_is_deterministic(seed):
    again = build()
    assert seed.keys() == again.keys()
    assert [k for k in seed if seed[k] != again[k]] == []


def test_scanned_midterms_have_no_text_layer(seed):
    scans = [k for k in seed if "midterm_scan_" in k]
    assert len(scans) == 20
    assert not any(_has_text(seed[k]) for k in scans)


def test_lecture_pdfs_do_have_a_text_layer(seed):
    decks = [k for k in seed if k.startswith("files/materials/ise3200/")]
    assert len(decks) == 11
    assert all(_has_text(seed[k]) for k in decks)


def test_ise_has_42_scored_questions_each_aligned_to_one_or_two_outcomes():
    questions = [q for a in ISE.assessments for q in a.questions]
    assert len(questions) == 42
    assert all(1 <= len(q.outcomes) <= 2 for q in questions)


def test_every_alignment_points_at_a_defined_outcome(seed):
    outcomes = json.loads(seed["canvas_json/courses/48213/outcomes.json"])
    alignments = json.loads(seed["manual/48213/question_outcomes.json"])
    ids = {o["id"] for o in outcomes}
    assert len(alignments) >= 42
    assert {a["outcome_id"] for a in alignments} <= ids


def test_twenty_students_and_one_teacher(seed):
    users = json.loads(seed["canvas_json/courses/48213/users.json"])
    types = [u["enrollments"][0]["type"] for u in users]
    assert types.count("StudentEnrollment") == 20
    assert types.count("TeacherEnrollment") == 1
