"""One tutor turn, following spec §11.3: scope -> mode -> retrieve -> generate -> verify -> log."""

import logging
from dataclasses import dataclass, field
from typing import Protocol

from tutor import prompts
from tutor.matcher import referenced_assessments
from tutor.models import (Assessment, Chunk, Learner, Mode, Move, PolicyDecision, Session, Turn,
                          TutorReply)
from tutor.policy import MODE_RULES, STAFF_ROLES, STRICTNESS, decide_mode, mode_for
from tutor.verifier import check_reply

log = logging.getLogger(__name__)

HISTORY_TURNS = 10
CHUNKS_PER_TURN = 6
MAX_ATTEMPTS = 2  # first draft + one stricter retry, then the rule-based fallback


class NotFound(Exception):
    """Unknown, or not this learner's. The router turns both into the same 404."""


class TutorRepo(Protocol):
    def assessments(self, course_id: str) -> list[Assessment]: ...
    def outcome_ids(self, course_id: str) -> set[str]: ...
    def answer_texts(self, course_id: str, assessment_ids: list[str]) -> list[str]: ...
    def weak_outcomes(self, course_id: str, learner_id: str) -> list[str]: ...
    def search(self, course_id: str, query: str, outcome_ids: list[str], k: int) -> list[Chunk]: ...
    def get_session(self, session_id: str) -> Session | None: ...
    def create_session(self, learner: Learner, mode: Mode, assessment_id: str | None,
                       outcome_id: str | None) -> Session: ...
    def set_session_mode(self, session_id: str, mode: Mode) -> None: ...
    def history(self, session_id: str, limit: int) -> list[Turn]: ...
    def add_turns(self, session_id: str, turns: list[dict]) -> None: ...


class TutorLLM(Protocol):
    def reply(self, system: str, messages: list[dict]) -> TutorReply: ...
    def leaks_answer(self, text: str, answer_texts: list[str]) -> bool: ...
    def references(self, message: str, candidates: list[Assessment],
                   current: Assessment | None = None) -> list[str]: ...


@dataclass
class TurnRequest:
    message: str
    session_id: str | None = None
    assessment_id: str | None = None
    outcome_id: str | None = None


@dataclass
class TurnResult:
    session_id: str
    mode: Mode
    reply: TutorReply
    citations: list[Chunk]
    fallback: bool
    decision: PolicyDecision
    violations: list[str] = field(default_factory=list)


class TutorService:
    def __init__(self, repo: TutorRepo, llm: TutorLLM):
        self.repo, self.llm = repo, llm

    def turn(self, learner: Learner, req: TurnRequest) -> TurnResult:
        session = self._session(learner, req)
        assessments = self.repo.assessments(learner.course_id)
        by_id = {a.id: a for a in assessments}
        target_id = req.assessment_id or (session.assessment_id if session else None)
        if target_id and target_id not in by_id:
            raise NotFound("assessment")
        target = by_id.get(target_id) if target_id else None
        if req.outcome_id and req.outcome_id not in self.repo.outcome_ids(learner.course_id):
            raise NotFound("outcome")

        restricted = [a for a in assessments if mode_for(a) is not Mode.STUDY]
        # Staff always get independent study, so there's nothing for the classifier to decide.
        matched = [] if learner.role in STAFF_ROLES else self._referenced(req.message, restricted, target)
        decision = decide_mode(learner.role, target, matched)
        rules = MODE_RULES[decision.mode]

        outcomes = list(dict.fromkeys(self.repo.weak_outcomes(learner.course_id, learner.learner_id)
                                      + ([req.outcome_id] if req.outcome_id else [])))
        chunks = self.repo.search(learner.course_id, req.message, outcomes, CHUNKS_PER_TURN)
        if target and decision.mode is Mode.STUDY and mode_for(target) is Mode.STUDY:
            chunks = [self._released_material(learner, target), *chunks]
        if session is None:
            session = self.repo.create_session(learner, decision.mode, target_id, req.outcome_id)
        elif STRICTNESS.index(decision.mode) < STRICTNESS.index(Mode(session.mode)):
            self.repo.set_session_mode(session.id, decision.mode)
        history = self.repo.history(session.id, HISTORY_TURNS)
        prev_hint = next((t.hint_level or 0 for t in reversed(history) if t.speaker == "tutor"), 0)
        answers = self.repo.answer_texts(learner.course_id, [a.id for a in restricted])

        reply, all_violations = None, []
        for _ in range(MAX_ATTEMPTS):
            messages = self._messages(history, chunks, req.message, rules, prev_hint, all_violations,
                                      target.title if target else None)
            try:
                draft = self.llm.reply(prompts.SYSTEM, messages)
            except Exception:
                log.exception("tutor model call failed")
                all_violations.append("model call failed")
                break
            violations = check_reply(draft, mode=decision.mode, retrieved_ids={c.id for c in chunks},
                                     prev_hint=prev_hint, answer_texts=answers, own_pseudonym=learner.pseudonym)
            # Runs in every mode: it's the backstop when the classifier misses a paraphrased question.
            if not violations and answers and self._model_says_leak(draft, answers):
                violations = ["reply paraphrases the answer key"]
            if not violations:
                reply = draft
                break
            all_violations += violations

        fallback = reply is None
        if fallback:
            reply = _fallback_reply(decision, chunks, by_id)
        cited = [c for c in chunks if c.id in set(reply.cited_chunk_ids)]

        self.repo.add_turns(session.id, [
            {"speaker": "student", "content": req.message},
            {"speaker": "tutor", "content": reply.message, "pedagogical_move": str(reply.move),
             "hint_level": reply.hint_level, "cited_chunk_ids": reply.cited_chunk_ids,
             "policy_decision": {"mode": str(decision.mode), "reason": decision.reason,
                                 "assessment_id": decision.assessment_id, "matched": decision.matched_codes,
                                 "rejected_drafts": all_violations, "fallback": fallback}},
        ])
        return TurnResult(session.id, decision.mode, reply, cited, fallback, decision, all_violations)

    # ------------------------------------------------------------------ steps

    def _session(self, learner: Learner, req: TurnRequest) -> Session | None:
        if not req.session_id:
            return None
        s = self.repo.get_session(req.session_id)
        if s is None or s.learner_id != learner.learner_id or s.course_id != learner.course_id:
            raise NotFound("session")
        return s

    def _referenced(self, message: str, restricted: list[Assessment],
                    target: Assessment | None) -> list[Assessment]:
        matched = referenced_assessments(message, restricted)
        if matched or not restricted:
            return matched
        try:
            codes = set(self.llm.references(message, restricted, target))
        except Exception:
            log.exception("reference classifier failed; treating the message as protected")
            return restricted
        return [a for a in restricted if a.code in codes]

    def _model_says_leak(self, draft: TutorReply, answers: list[str]) -> bool:
        try:
            return self.llm.leaks_answer(f"{draft.message}\n{draft.next_step}", answers)
        except Exception:
            log.exception("leak checker failed; rejecting the draft")
            return True

    def _released_material(self, learner: Learner, target: Assessment) -> Chunk:
        """A released assessment's own questions (and its key, once answers are released) as citable material.
        Only reached in independent study for an assessment that is itself released; open ones never get here."""
        text = target.text
        if target.answers_released:
            key = "\n".join(self.repo.answer_texts(learner.course_id, [target.id]))
            text += f"\n\nAnswer key (released):\n{key}" if key else ""
        return Chunk(f"assessment-{target.id}", target.title, text, "assessment", None, None, None)

    @staticmethod
    def _messages(history: list[Turn], chunks: list[Chunk], message: str, rules, prev_hint: int,
                  violations: list[str], working_on: str | None) -> list[dict]:
        msgs = [{"role": "user" if t.speaker == "student" else "assistant", "content": t.content} for t in history]
        msgs.append({"role": "user", "content": prompts.user_turn(chunks, message)})
        msgs.append({"role": "system", "content": prompts.mode_note(rules, prev_hint, violations, working_on)})
        return msgs


def _fallback_reply(decision: PolicyDecision, chunks: list[Chunk], by_id: dict[str, Assessment]) -> TutorReply:
    """Rule-based reply used when the model is down or keeps failing verification (spec §16 fallback)."""
    top = chunks[:2]
    where = "; ".join(f"{c.title} ({prompts.locator(c)})" for c in top)
    if decision.mode is Mode.PROTECTED:
        code = by_id[decision.assessment_id].code if decision.assessment_id in by_id else "this assessment"
        message = f"I can't help with {code} while it's open for grading."
        if where:
            message += f" These course materials cover the ideas behind it: {where}."
        return TutorReply(message=message, move=Move.DECLINE, hint_level=0, cited_chunk_ids=[c.id for c in top],
                          next_step="Review the material, then ask me about the general concept.")
    message = "I couldn't put together a reliable answer just now."
    message += f" A good place to start: {where}. Which part is unclear?" if where else " Which part is unclear?"
    return TutorReply(message=message, move=Move.ASK, hint_level=0, cited_chunk_ids=[c.id for c in top],
                      next_step="Tell me which step you're stuck on.")
