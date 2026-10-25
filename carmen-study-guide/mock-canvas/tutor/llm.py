"""Claude calls. Opus writes tutor replies; Haiku does the cheap classification and leak checks.

Needs ANTHROPIC_API_KEY (server-side only). For a free local alternative, see llm_ollama.py.
"""

import os

import anthropic

from tutor import prompts
from tutor.models import Assessment, LeakVerdict, ReferenceVerdict, TutorReply

TUTOR_MODEL = "claude-opus-5-5"
CHECK_MODEL = "claude-haiku-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

__all__ = ["AnthropicTutorLLM", "BedrockTutorLLM", "ModelRefused", "LeakVerdict", "ReferenceVerdict", "TUTOR_MODEL",
           "CHECK_MODEL"]


class ModelRefused(Exception):
    pass


class AnthropicTutorLLM:
    def __init__(self, client=None, effort: str = "low"):
        self.client = client or anthropic.Anthropic()
        self.effort = effort
        self.check_model = CHECK_MODEL

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

    def leaks_answer(self, text: str, answer_texts: list[str], question: str | None = None) -> bool:
        content = prompts.leak_check_content(text, answer_texts, question)
        return self._check(prompts.LEAK_SYSTEM, content, LeakVerdict).leaks

    def references(self, message: str, candidates: list[Assessment], current: Assessment | None = None) -> list[str]:
        content = prompts.reference_check_content(message, candidates, current)
        codes = self._check(prompts.REFERENCE_SYSTEM, content, ReferenceVerdict).assessment_codes
        known = {a.code for a in candidates}
        return [c for c in codes if c in known]

    def _check(self, system: str, content: str, schema):
        response = self.client.messages.parse(
            model=self.check_model,
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


# The OSU AWS account can only invoke these through Bedrock's InvokeModel endpoint (newer models and the
# bedrock-mantle endpoint are blocked there). Override with BEDROCK_TUTOR_MODEL / BEDROCK_CHECK_MODEL.
BEDROCK_TUTOR_MODEL = "us.anthropic.claude-opus-4-6-v1"
BEDROCK_CHECK_MODEL = "us.anthropic.claude-sonnet-4-6"


class BedrockTutorLLM(AnthropicTutorLLM):
    """Claude on Amazon Bedrock, using AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN / AWS_REGION.

    Differences from the Claude API path: no server-side refusal fallback (the service's own fallback covers
    refusals), no top-level automatic caching (older Bedrock models reject it), and the per-turn mode note goes in
    the system prompt because 4.6 models don't accept system messages mid-conversation.
    """

    def __init__(self, client=None, effort: str = "low"):
        client = client or anthropic.AnthropicBedrock(
            aws_access_key=os.environ.get("AWS_ACCESS_KEY_ID"), aws_secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.environ.get("AWS_SESSION_TOKEN"), aws_region=os.environ.get("AWS_REGION", "us-east-2"))
        super().__init__(client, effort)
        self.tutor_model = os.environ.get("BEDROCK_TUTOR_MODEL") or BEDROCK_TUTOR_MODEL
        self.check_model = os.environ.get("BEDROCK_CHECK_MODEL") or BEDROCK_CHECK_MODEL

    def reply(self, system: str, messages: list[dict]) -> TutorReply:
        notes = [{"type": "text", "text": m["content"]} for m in messages if m["role"] == "system"]
        response = self.client.messages.parse(
            model=self.tutor_model,
            max_tokens=16000,
            thinking={"type": "adaptive"},  # 4.6 models only think when asked explicitly
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}, *notes],
            messages=[m for m in messages if m["role"] != "system"],
            output_config={"effort": self.effort},
            output_format=TutorReply,
        )
        return self._parsed(response)
