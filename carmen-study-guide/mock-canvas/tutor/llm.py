"""Claude calls. Opus writes tutor replies; Haiku does the cheap classification and leak checks.

Needs ANTHROPIC_API_KEY (server-side only). For a free local alternative, see llm_ollama.py.
"""

import anthropic

from tutor import prompts
from tutor.models import Assessment, LeakVerdict, ReferenceVerdict, TutorReply

TUTOR_MODEL = "claude-opus-5-5"
CHECK_MODEL = "claude-haiku-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

__all__ = ["AnthropicTutorLLM", "ModelRefused", "LeakVerdict", "ReferenceVerdict", "TUTOR_MODEL", "CHECK_MODEL"]


class ModelRefused(Exception):
    pass


class AnthropicTutorLLM:
    def __init__(self, client=None, effort: str = "low"):
        self.client = client or anthropic.Anthropic()
        self.effort = effort

    def reply(self, system: str, messages: list[dict]) -> TutorReply:
        response = self.client.beta.messages.parse(
            model=TUTOR_MODEL,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            cache_control={"type": "ephemeral"},  # caches the growing session history between turns
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": self.effort},
            output_format=TutorReply,
        )
        return self._parsed(response)

    def leaks_answer(self, text: str, answer_texts: list[str]) -> bool:
        content = prompts.leak_check_content(text, answer_texts)
        return self._check(prompts.LEAK_SYSTEM, content, LeakVerdict).leaks

    def references(self, message: str, candidates: list[Assessment], current: Assessment | None = None) -> list[str]:
        content = prompts.reference_check_content(message, candidates, current)
        codes = self._check(prompts.REFERENCE_SYSTEM, content, ReferenceVerdict).assessment_codes
        known = {a.code for a in candidates}
        return [c for c in codes if c in known]

    def _check(self, system: str, content: str, schema):
        response = self.client.messages.parse(
            model=CHECK_MODEL,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "low"},
            output_format=schema,
        )
        return self._parsed(response)

    @staticmethod
    def _parsed(response):
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ModelRefused(f"stop_reason={response.stop_reason}")
        return response.parsed_output
