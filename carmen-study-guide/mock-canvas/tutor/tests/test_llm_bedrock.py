import pytest

from tutor.llm_bedrock import ConverseTutorLLM
from tutor.tests.fakes import QUIZ2, good


class FakeRuntime:
    """Stands in for boto3's bedrock-runtime client: records converse() calls, answers with queued tool inputs."""

    def __init__(self, *tool_inputs, stop="tool_use"):
        self.inputs, self.stop, self.calls = list(tool_inputs), stop, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"]
        return {"stopReason": self.stop,
                "output": {"message": {"role": "assistant", "content": [
                    {"text": "thinking out loud"},
                    {"toolUse": {"toolUseId": "t1", "name": name, "input": self.inputs.pop(0)}}]}}}


def llm(runtime):
    return ConverseTutorLLM(runtime, tutor_model="us.amazon.nova-pro-v1:0", check_model="us.amazon.nova-2-lite-v1:0")


def test_reply_forces_the_schema_tool_and_parses_it():
    rt = FakeRuntime(good().model_dump(mode="json"))
    assert llm(rt).reply("SYSTEM", [{"role": "user", "content": "hi"}, {"role": "system", "content": "Mode: guided"}]) == good()
    call = rt.calls[0]
    assert call["modelId"] == "us.amazon.nova-pro-v1:0"
    assert [s["text"] for s in call["system"]] == ["SYSTEM", "Mode: guided"]  # mode note goes in system
    assert call["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
    tool = call["toolConfig"]["tools"][0]["toolSpec"]
    assert call["toolConfig"]["toolChoice"] == {"tool": {"name": tool["name"]}}
    schema = tool["inputSchema"]["json"]
    assert {"message", "move", "snippets"} <= set(schema["properties"]) and "$defs" not in schema


def test_history_is_merged_into_alternating_turns():
    rt = FakeRuntime(good().model_dump(mode="json"))
    llm(rt).reply("S", [{"role": "user", "content": "a"}, {"role": "user", "content": "b"},
                        {"role": "assistant", "content": "c"}, {"role": "user", "content": "d"}])
    assert [m["role"] for m in rt.calls[0]["messages"]] == ["user", "assistant", "user"]
    assert rt.calls[0]["messages"][0]["content"] == [{"text": "a"}, {"text": "b"}]


def test_reply_that_does_not_match_the_schema_raises_so_the_service_falls_back():
    with pytest.raises(ValueError):
        llm(FakeRuntime({"message": "hi"})).reply("S", [{"role": "user", "content": "hi"}])


def test_checks_use_the_small_model():
    rt = FakeRuntime({"leaks": True, "reason": "gives C"}, {"assessment_codes": ["Quiz 2", "Made Up"]})
    model = llm(rt)
    assert model.leaks_answer("text", ["2. C: x"], "what is it?") is True
    assert model.references("the list one", [QUIZ2]) == ["Quiz 2"]
    assert all(c["modelId"] == "us.amazon.nova-2-lite-v1:0" for c in rt.calls)
    assert "<student_question>" in rt.calls[0]["messages"][0]["content"][0]["text"]
