"""Deterministic output checks (spec §11.1 verifier). The model-based paraphrase check lives in llm.py."""

import re

from tutor.models import Mode, Move, TutorReply
from tutor.policy import MODE_RULES

# Normalized characters. Shorter fragments ("B", "[1, 2]", "an empty list") also appear in innocent replies, so
# they're left to the model-based paraphrase check.
MIN_ANSWER_FRAGMENT = 20
PSEUDONYM = re.compile(r"\bS-[0-9a-f]{10}\b")
NO_CITATION_NEEDED = {Move.ASK, Move.DECLINE}


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


KEY_PREFIX = re.compile(r"^\s*(\d+\s*[.)]\s*)?([A-Za-z]\s*[.:)]\s+)?")  # "2. C: ..." -> "..."


def _fragments(answer_texts: list[str]) -> list[str]:
    parts = (KEY_PREFIX.sub("", p) for t in answer_texts for p in re.split(r"[\n;]+", t))
    return [n for n in map(_norm, parts) if len(n) >= MIN_ANSWER_FRAGMENT]


def shown_text(reply: TutorReply) -> str:
    """Everything the student would see, quotes included: what the leak and privacy checks inspect."""
    return "\n".join([reply.message, reply.next_step, *(s.quote for s in reply.snippets)])


def check_reply(reply: TutorReply, *, mode: Mode, retrieved_ids: set[str], prev_hint: int,
                answer_texts: list[str], own_pseudonym: str) -> list[str]:
    """Return human-readable violations; empty means the reply may be shown."""
    rules = MODE_RULES[mode]
    violations = []

    if reply.move not in rules.moves:
        violations.append(f"move '{reply.move}' is not allowed in {mode}")
    if not 0 <= reply.hint_level <= rules.max_hint:
        violations.append(f"hint_level {reply.hint_level} is outside 0..{rules.max_hint} for {mode}")
    elif reply.hint_level > prev_hint + 1:
        violations.append(f"hint_level jumped from {prev_hint} to {reply.hint_level}; raise it by at most 1")

    unknown = set(reply.cited_chunk_ids) - retrieved_ids
    if unknown:
        violations.append(f"citation to material that was not retrieved: {sorted(unknown)}")
    elif retrieved_ids and not reply.cited_chunk_ids and reply.move not in NO_CITATION_NEEDED:
        violations.append("reply must cite at least one course_material block")

    shown = shown_text(reply)
    text = _norm(shown)
    if any(f in text for f in _fragments(answer_texts)):
        violations.append("reply contains answer key text")

    if any(p != own_pseudonym for p in PSEUDONYM.findall(shown)):
        violations.append("reply mentions another student's id")
    return violations
