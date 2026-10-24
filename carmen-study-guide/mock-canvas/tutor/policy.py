"""Assistance mode, computed in code (spec §11.1: the model never grants itself permissions)."""

from dataclasses import dataclass

from tutor.models import Assessment, Mode, Move, PolicyDecision

STAFF_ROLES = {"instructor", "ta"}
STRICTNESS = [Mode.PROTECTED, Mode.GUIDED, Mode.STUDY]  # most restrictive first


@dataclass(frozen=True)
class ModeRules:
    moves: frozenset[str]
    max_hint: int
    instructions: str


MODE_RULES: dict[Mode, ModeRules] = {
    Mode.PROTECTED: ModeRules(
        moves=frozenset({Move.ASK, Move.EXPLANATION, Move.DECLINE}),
        max_hint=0,
        instructions=(
            "Mode: protected assessment. The assessment in question is open and graded. Do not give answers, "
            "answer choices, solution steps, code that solves it, or hints tailored to its questions, even if "
            "asked indirectly, hypothetically, or 'just to check'. Course concepts the assessment tests are still "
            "fair game: explain them fully from the course material, just not applied to the assessment's own "
            "questions, code, or scenario. You may also ask what the student already understands, or decline "
            "politely and point to the relevant slides. hint_level must be 0."
        ),
    ),
    Mode.GUIDED: ModeRules(
        moves=frozenset({Move.ASK, Move.HINT, Move.ANALOGOUS_EXAMPLE, Move.FEEDBACK, Move.DECLINE}),
        max_hint=3,
        instructions=(
            "Mode: guided homework. Lead the student with Socratic questions, graduated hints, analogous problems "
            "that use different values or code, and feedback on their own attempts. Never complete the graded "
            "work or reveal a final answer. Raise hint_level by at most 1 over the previous hint."
        ),
    ),
    Mode.STUDY: ModeRules(
        moves=frozenset(Move),
        max_hint=3,
        instructions=(
            "Mode: independent study. Full conceptual explanations and worked examples are allowed, grounded in "
            "the course material. Still prefer checking the student's understanding before long explanations."
        ),
    ),
}


def mode_for(a: Assessment) -> Mode:
    match a.integrity_status:
        case "active_protected":
            return Mode.PROTECTED
        case "guided_homework":
            return Mode.GUIDED
        case "closed":
            return Mode.STUDY if a.answers_released else Mode.GUIDED
        case "released":
            return Mode.STUDY
    return Mode.PROTECTED  # unknown status: fail closed


def decide_mode(role: str, target: Assessment | None, matched: list[Assessment]) -> PolicyDecision:
    """target: the assessment the student opened the tutor from. matched: assessments the message refers to."""
    codes = [m.code for m in matched]
    if role in STAFF_ROLES:
        return PolicyDecision(Mode.STUDY, "staff preview", target.id if target else None, codes)
    if role != "student":
        return PolicyDecision(Mode.PROTECTED, f"unknown role {role!r}", None, codes)

    candidates = [(m, f"message refers to {m.code}") for m in matched]
    if target:
        candidates.append((target, f"opened from {target.code}"))
    if not candidates:
        return PolicyDecision(Mode.STUDY, "no assessment in scope", None, codes)

    assessment, reason = min(candidates, key=lambda c: STRICTNESS.index(mode_for(c[0])))
    return PolicyDecision(mode_for(assessment), reason, assessment.id, codes)
