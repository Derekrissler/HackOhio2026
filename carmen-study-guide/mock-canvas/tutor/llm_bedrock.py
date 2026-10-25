"""Non-Claude models on Amazon Bedrock (Converse API), paid from AWS credits. Default: Amazon Nova.

Every integrity rule is still enforced in code (policy, retrieval filter, verifier, fallback); the model only
changes how often drafts pass the checks. Structured output comes from a forced "tool" whose input schema is the
reply schema. Uses AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN / AWS_REGION from the environment.
"""

import os

from pydantic import ValidationError

from tutor import prompts
from tutor.llm_ollama import flat_schema
from tutor.models import Assessment, LeakVerdict, ReferenceVerdict, TutorReply

DEFAULT_TUTOR_MODEL = "us.amazon.nova-pro-v1:0"
DEFAULT_CHECK_MODEL = "us.amazon.nova-2-lite-v1:0"


class ConverseTutorLLM:
    def __init__(self, runtime=None, tutor_model: str | None = None, check_model: str | None = None):
        if runtime is None:
            import boto3
            runtime = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-2"))
        self.runtime = runtime
        self.tutor_model = tutor_model or os.environ.get("BEDROCK_TUTOR_MODEL") or DEFAULT_TUTOR_MODEL
        self.check_model = check_model or os.environ.get("BEDROCK_CHECK_MODEL") or DEFAULT_CHECK_MODEL

    def reply(self, system: str, messages: list[dict]) -> TutorReply:
        notes = [m["content"] for m in messages if m["role"] == "system"]
        turns = [m for m in messages if m["role"] != "system"]
        return self._structured(self.tutor_model, [system, *notes], turns, TutorReply, max_tokens=3000)

    def leaks_answer(self, text: str, answer_texts: list[str], question: str | None = None) -> bool:
        content = prompts.leak_check_content(text, answer_texts, question)
        return self._structured(self.check_model, [prompts.LEAK_SYSTEM], [{"role": "user", "content": content}],
                                LeakVerdict).leaks

    def references(self, message: str, candidates: list[Assessment], current: Assessment | None = None) -> list[str]:
        content = prompts.reference_check_content(message, candidates, current)
        codes = self._structured(self.check_model, [prompts.REFERENCE_SYSTEM],
                                 [{"role": "user", "content": content}], ReferenceVerdict).assessment_codes
        known = {a.code for a in candidates}
        return [c for c in codes if c in known]

    def _structured(self, model: str, system: list[str], turns: list[dict], schema, max_tokens: int = 800):
        name = f"submit_{schema.__name__.lower()}"
        response = self.runtime.converse(
            modelId=model,
            system=[{"text": s} for s in system],
            messages=_alternating(turns),
            toolConfig={"tools": [{"toolSpec": {"name": name, "description": f"Return the {schema.__name__}.",
                                                "inputSchema": {"json": flat_schema(schema)}}}],
                        "toolChoice": {"tool": {"name": name}}},
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )
        for block in response["output"]["message"]["content"]:
            if "toolUse" in block and block["toolUse"]["name"] == name:
                try:
                    return schema.model_validate(block["toolUse"]["input"])
                except ValidationError as e:
                    raise ValueError(f"{model} returned an invalid {schema.__name__}") from e
        raise ValueError(f"{model} did not return {schema.__name__} (stop: {response.get('stopReason')})")


def _alternating(turns: list[dict]) -> list[dict]:
    """Converse needs user/assistant to alternate and start with user; merge neighbours with the same role."""
    out: list[dict] = []
    for t in turns:
        block = {"text": t["content"]}
        if out and out[-1]["role"] == t["role"]:
            out[-1]["content"].append(block)
        else:
            out.append({"role": t["role"], "content": [block]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out
