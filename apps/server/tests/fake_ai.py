"""Turn the simple drafts these tests write into what the ingest agent expects.

Tests write key points as plain strings. The ingest agent wants each point to
name the numbered passage that states it, so ``cited`` points each string at
the first passage it was shown that contains the point's numbers (or the
first passage, for a point without numbers).
"""

from __future__ import annotations

import re
from typing import Any

_PASSAGE = re.compile(r"^\[(\d+)\] (.*)$", re.M)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _passage_for(point: str, user: str) -> int:
    shown = [(int(n), text) for n, text in _PASSAGE.findall(user)]
    numbers = {n.replace(",", "") for n in _NUMBER.findall(point)}
    for n, text in shown:
        if numbers <= {m.replace(",", "") for m in _NUMBER.findall(text)}:
            return n
    return shown[0][0] if shown else 1


def cited(data: dict[str, Any], user: str, schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("title") == "Fixes":
        return {"fixes": []}
    points = data.get("key_points")
    if not isinstance(points, list) or not all(isinstance(p, str) for p in points):
        return data
    out = dict(data)
    out["key_points"] = [
        {"text": p, "first": (n := _passage_for(p, user)), "last": n} for p in points
    ]
    return out
