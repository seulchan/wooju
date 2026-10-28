"""What the paid AI (an OpenAI or Claude API key) has been used for, this month.

Each call's tokens, as the provider reports them, are appended to
``usage.jsonl`` in the app's data folder (never the Brain, never the key).
Settings shows the month's totals and, for models whose price is in the table
below, an estimate in US dollars. The estimate is never the bill: prices
change, and the provider's own usage page is the source of truth. A call the
provider did not report tokens for counts as unknown, not as zero; a model
not in the table has no estimate rather than a guess.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brain_core.changes import data_dir
from wooju_agents.llm import LLMResult

# US dollars per million tokens (input, output), standard rates for prompts
# the size Wooju sends. Checked against the providers' pricing pages on the
# date below; update both together.
PRICES_CHECKED = "2026-10-28"
PRICES: dict[str, tuple[float, float]] = {
    # https://platform.claude.com/docs/en/about-claude/pricing (Haiku: prompts ≤ 100K tokens)
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    # https://developers.openai.com/api/docs/models/gpt-5-mini
    "gpt-5-mini": (0.25, 2.0),
}
BILLING_PAGES = {
    "openai": "https://platform.openai.com/usage",
    "anthropic": "https://platform.claude.com/usage",
}

_lock = threading.Lock()


def usage_file() -> Path:
    return data_dir() / "usage.jsonl"


def record(result: LLMResult) -> None:
    """Append one paid call. Best effort: a full disk must not fail the call."""
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": result.provider,
        "model": result.model,
        "input": result.input_tokens,
        "output": result.output_tokens,
    }
    try:
        path = usage_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def price_for(model: str) -> tuple[float, float] | None:
    """The table's price for a model, also for a dated id ("gpt-5-mini-2025-08-07")."""
    if model in PRICES:
        return PRICES[model]
    for name, price in PRICES.items():
        if model.startswith(name + "-"):
            return price
    return None


def month_summary(month: str | None = None) -> dict[str, Any]:
    """Totals per model for ``month`` ("YYYY-MM", default this month)."""
    month = month or datetime.now(UTC).strftime("%Y-%m")
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        lines = usage_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict) or not str(e.get("at", "")).startswith(month):
            continue
        key = (str(e.get("provider")), str(e.get("model")))
        row = rows.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "unknown_calls": 0,
            },
        )
        row["calls"] += 1
        if isinstance(e.get("input"), int) and isinstance(e.get("output"), int):
            row["input_tokens"] += e["input"]
            row["output_tokens"] += e["output"]
        else:
            row["unknown_calls"] += 1
    total = 0.0
    priced_all = True
    for row in rows.values():
        price = price_for(row["model"])
        if price is None:
            row["cost_usd"] = None
            priced_all = False
            continue
        cost = (row["input_tokens"] * price[0] + row["output_tokens"] * price[1]) / 1_000_000
        row["cost_usd"] = round(cost, 4)
        total += cost
        priced_all = priced_all and not row["unknown_calls"]
    return {
        "month": month,
        "rows": sorted(rows.values(), key=lambda r: (-r["calls"], r["model"])),
        "cost_usd": round(total, 4),
        "complete": priced_all,
        "prices_checked": PRICES_CHECKED,
        "billing_pages": BILLING_PAGES,
    }
