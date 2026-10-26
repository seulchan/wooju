from __future__ import annotations

import json

import httpx
import pytest

from wooju_agents.llm import (
    AnthropicProvider,
    LLMError,
    OllamaProvider,
    OpenAIProvider,
    recommended_ollama_model,
)
from wooju_agents.text import normalize_korean, resolve_language

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}}


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_sends_schema_and_parses():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"a": 1}'}})

    result = OllamaProvider("qwen3.5:4b", client=client(handler)).generate_json("s", "u", SCHEMA)
    assert result.data == {"a": 1}
    assert (
        seen["format"] == SCHEMA and seen["think"] is False and seen["options"]["temperature"] == 0
    )


def test_ollama_retries_without_think_for_models_that_reject_it():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append("think" in body)
        if "think" in body:
            return httpx.Response(400, text='{"error":"model does not support think"}')
        return httpx.Response(200, json={"message": {"content": '{"a": 2}'}})

    assert OllamaProvider("m", client=client(handler)).generate_json("s", "u", SCHEMA).data == {
        "a": 2
    }
    assert calls == [True, False]


def test_ollama_errors_have_user_messages():
    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError) as exc:
        OllamaProvider("m", client=client(down)).generate_json("s", "u", SCHEMA)
    assert "Ollama" in exc.value.user_message

    missing = client(lambda r: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError) as exc:
        OllamaProvider("qwen3.5:9b", client=missing).generate_json("s", "u", SCHEMA)
    assert "qwen3.5:9b" in exc.value.user_message


def test_ollama_status():
    tags = client(lambda r: httpx.Response(200, json={"models": [{"name": "qwen3.5:4b"}]}))
    assert OllamaProvider("qwen3.5:4b", client=tags).status() == {
        "running": True,
        "models": ["qwen3.5:4b"],
        "model_ready": True,
    }

    def down(request):
        raise httpx.ConnectError("refused")

    assert OllamaProvider("x", client=client(down)).status()["running"] is False


def test_openai_uses_json_schema_response_format():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 3}'}}]})

    assert OpenAIProvider("sk-test", client=client(handler)).generate_json(
        "s", "u", SCHEMA
    ).data == {"a": 3}
    assert seen["auth"] == "Bearer sk-test"
    assert seen["response_format"]["json_schema"]["schema"] == SCHEMA


def test_anthropic_forces_tool_call():
    seen = {}

    def handler(request):
        seen["key"] = request.headers["x-api-key"]
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "tool_use", "input": {"a": 4}}]})

    assert AnthropicProvider("k", client=client(handler)).generate_json("s", "u", SCHEMA).data == {
        "a": 4
    }
    assert seen["tool_choice"] == {"type": "tool", "name": "output"}
    assert seen["tools"][0]["input_schema"] == SCHEMA


def test_bad_keys_say_so():
    unauthorized = client(lambda r: httpx.Response(401, json={}))
    with pytest.raises(LLMError) as exc:
        OpenAIProvider("bad", client=unauthorized).generate_json("s", "u", SCHEMA)
    assert "API 키" in exc.value.user_message
    with pytest.raises(LLMError) as exc:
        AnthropicProvider("bad", client=unauthorized).generate_json("s", "u", SCHEMA)
    assert "API 키" in exc.value.user_message


def test_invalid_json_is_an_error():
    bad = client(lambda r: httpx.Response(200, json={"message": {"content": "not json"}}))
    with pytest.raises(LLMError):
        OllamaProvider("m", client=bad).generate_json("s", "u", SCHEMA)


def test_recommended_model_by_memory():
    assert recommended_ollama_model(8 * 1024**3) == "qwen3.5:4b"
    assert recommended_ollama_model(16 * 1024**3) == "qwen3.5:9b"


def test_normalize_korean():
    assert (
        normalize_korean("2026 년 7 월 3 차, 1 배, 600 개, 75 %")
        == "2026년 7월 3차, 1배, 600개, 75%"
    )
    assert normalize_korean("3 times 2026 년") == "3 times 2026년"


def test_resolve_language(monkeypatch):
    assert resolve_language("ko") == "ko"
    assert resolve_language("fr") == "en"
    monkeypatch.setenv("WOOJU_LANGUAGE", "ko")
    assert resolve_language("auto") == "ko"
