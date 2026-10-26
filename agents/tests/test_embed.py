import httpx
import pytest

from wooju_agents.embed import Embedder
from wooju_agents.llm import LLMError


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_query_is_normalized_and_instructed():
    seen = {}

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3-embedding:0.6b"}]})
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0]]})

    e = Embedder(client=_client(handler))
    assert e.ready()
    vec = e.query("밸류업?")
    assert [round(x, 3) for x in vec] == [0.6, 0.8]
    assert "Instruct:" in seen["body"] and "qwen3-embedding:0.6b" in seen["body"]


def test_documents_in_batches():
    calls = []

    def handler(request):
        import json

        n = len(json.loads(request.read())["input"])
        calls.append(n)
        return httpx.Response(200, json={"embeddings": [[1.0]] * n})

    assert len(Embedder(client=_client(handler)).documents(["t"] * 20)) == 20
    assert calls == [16, 4]


def test_missing_model_is_retryable():
    e = Embedder(client=_client(lambda r: httpx.Response(404, json={"error": "not found"})))
    with pytest.raises(LLMError) as err:
        e.documents(["x"])
    assert err.value.retryable
    assert not Embedder(client=_client(lambda r: httpx.Response(200, json={"models": []}))).ready()
