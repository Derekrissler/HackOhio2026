"""Cheap, deterministic check for messages that name or paste from an assessment.

Only strong signals count here; anything subtler goes to the model classifier. Exams quote core course ideas
("the five parts of a good prompt"), so a short shared phrase is not evidence of pasting, but shared code is.
"""

import re

from tutor.models import Assessment

CODE_SHINGLE = 6   # tokens, punctuation included: "def add ( x , items"
PROSE_SHINGLE = 10  # consecutive words: a real paste of question text


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+|[^\sa-z0-9_]", text.lower())


def _shingles(seq: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(seq[i:i + n]) for i in range(len(seq) - n + 1)}


def _code_shingles(text: str) -> set[tuple[str, ...]]:
    """Token runs that look like code: at least two symbols and two identifiers."""
    def is_word(t):
        return t[0].isalnum() or t[0] == "_"
    return {s for s in _shingles(_tokens(text), CODE_SHINGLE)
            if sum(not is_word(t) for t in s) >= 2 and sum(is_word(t) for t in s) >= 2}


def _names(message_words: list[str], code: str) -> bool:
    code_words = _words(code)
    n = len(code_words)
    return n > 0 and any(message_words[i:i + n] == code_words for i in range(len(message_words) - n + 1))


def referenced_assessments(message: str, assessments: list[Assessment]) -> list[Assessment]:
    words = _words(message)
    prose = _shingles(words, PROSE_SHINGLE)
    code = _code_shingles(message)
    return [a for a in assessments
            if _names(words, a.code)
            or (code and code & _code_shingles(a.text))
            or (prose and prose & _shingles(_words(a.text), PROSE_SHINGLE))]
