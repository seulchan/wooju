"""This month's paid AI usage: recorded per call, estimated only where the price is known."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import usage
from app.main import app
from wooju_agents.llm import LLMResult


def result(model: str, i: int | None, o: int | None, provider: str = "anthropic") -> LLMResult:
    return LLMResult({}, "", 0.1, provider, model, i, o)


def test_the_month_is_summed_per_model_with_an_estimate():
    usage.record(result("claude-haiku-5-5", 1_000_000, 100_000))
    usage.record(result("claude-haiku-5-5", 1_000_000, None))  # tokens not reported
    usage.record(result("gpt-5-mini-2025-08-07", 2_000_000, 1_000_000, "openai"))
    usage.record(result("some-new-model", 500, 50, "openai"))
    s = usage.month_summary()
    rows = {r["model"]: r for r in s["rows"]}
    haiku = rows["claude-haiku-5-5"]
    assert haiku["calls"] == 2 and haiku["unknown_calls"] == 1
    assert haiku["input_tokens"] == 1_000_000 and haiku["cost_usd"] == pytest.approx(0.15)
    assert rows["gpt-5-mini-2025-08-07"]["cost_usd"] == pytest.approx(2.5)
    assert rows["some-new-model"]["cost_usd"] is None  # no price: no guess
    assert s["cost_usd"] == pytest.approx(2.65) and s["complete"] is False


def test_other_months_and_broken_lines_are_left_out():
    path = usage.usage_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"at": "2020-01-01T00:00:00+00:00", "provider": "openai", "model": "x"})
        + "\nnot json\n",
        encoding="utf-8",
    )
    assert usage.month_summary()["rows"] == []
    assert usage.month_summary("2020-01")["rows"][0]["calls"] == 1


def test_usage_api():
    usage.record(result("claude-haiku-5-5", 10, 2))
    with TestClient(app) as c:
        body = c.get("/api/usage").json()
    assert body["rows"][0]["model"] == "claude-haiku-5-5"
    assert body["prices_checked"] and body["billing_pages"]["anthropic"].startswith("https://")
