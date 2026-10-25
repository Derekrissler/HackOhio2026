"""Local, free alternative to llm.py: the same three calls against an Ollama server.

Every integrity rule is still enforced in code (policy, retrieval filter, verifier, fallback); a local model only
changes how often drafts pass the checks. Set TUTOR_LLM=ollama in mock-canvas/.env, then:

    ollama pull qwen2.5:7b      # tutor replies
    ollama pull qwen2.5:3b      # the quick reference / leak checks
"""

import os

import requests

from tutor import prompts
from tutor.models import Assessment, LeakVerdict, ReferenceVerdict, TutorReply

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_TUTOR_MODEL = "qwen2.5:7b"
DEFAULT_CHECK_MODEL = "qwen2.5:3b"
TIMEOUT = 180  # seconds; CPU-only machines are slow


def flat_schema(model) -> dict:
    """Pydantic puts enums in $defs and points at them with $ref; inline them so any Ollama version can use it."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {k: inline(v) for k, v in node.items()}
        return [inline(v) for v in node] if isinstance(node, list) else node

    return inline(schema)


class OllamaUnavailable(RuntimeError):
    """Ollama isn't running or a model isn't pulled. RuntimeError, so the tutor answers 503 with the message."""


class OllamaTutorLLM:
    def __init__(self, http=requests, url: str | None = None, tutor_model: str | None = None,
                 check_model: str | None = None):
        self.http = http
        self.url = (url or os.environ.get("OLLAMA_URL") or DEFAULT_URL).rstrip("/")
        self.tutor_model = tutor_model or os.environ.get("OLLAMA_TUTOR_MODEL") or DEFAULT_TUTOR_MODEL
        self.check_model = check_model or os.environ.get("OLLAMA_CHECK_MODEL") or DEFAULT_CHECK_MODEL

    def check_ready(self) -> None:
        try:
            tags = self.http.get(f"{self.url}/api/tags", timeout=5).json()
        except Exception:
            raise OllamaUnavailable(f"Ollama isn't reachable at {self.url}. Install it and run `ollama serve`.")
        have = {m["name"] for m in tags.get("models", [])}
        for model in (self.tutor_model, self.check_model):
            if model not in have and f"{model}:latest" not in have:
                raise OllamaUnavailable(f"Model {model} isn't installed. Run `ollama pull {model}`.")

    def reply(self, system: str, messages: list[dict]) -> TutorReply:
        content = self._chat(self.tutor_model, [{"role": "system", "content": system}, *messages], TutorReply)
        return TutorReply.model_validate_json(content)

    def leaks_answer(self, text: str, answer_texts: list[str], question: str | None = None) -> bool:
        content = self._chat(self.check_model, [
            {"role": "system", "content": prompts.LEAK_SYSTEM},
            {"role": "user", "content": prompts.leak_check_content(text, answer_texts, question)},
        ], LeakVerdict)
        return LeakVerdict.model_validate_json(content).leaks

    def references(self, message: str, candidates: list[Assessment], current: Assessment | None = None) -> list[str]:
        content = self._chat(self.check_model, [
            {"role": "system", "content": prompts.REFERENCE_SYSTEM},
            {"role": "user", "content": prompts.reference_check_content(message, candidates, current)},
        ], ReferenceVerdict)
        known = {a.code for a in candidates}
        return [c for c in ReferenceVerdict.model_validate_json(content).assessment_codes if c in known]

    def _chat(self, model: str, messages: list[dict], schema) -> str:
        """Ollama structured output: `format` takes a JSON schema and constrains the reply to it."""
        r = self.http.post(f"{self.url}/api/chat", json={
            "model": model, "messages": messages, "format": flat_schema(schema), "stream": False,
            "options": {"temperature": 0.2},
        }, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()["message"]["content"]
