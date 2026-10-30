"""How the user decides on what agents propose: a measure of the review gate.

The gate is only worth having if it is used. Anthropic reported that Claude
Code users approve 93% of permission prompts; a gate approved that readily
passes the model's errors on with the user's signature. So every decision on
a proposal (approved as is, approved after editing, rejected; one by one or in
a batch) is appended to ``approvals.jsonl`` in the app's data folder, never
the Brain, and Settings shows the last 30 days. A high "approved as is" rate
is the signal to rethink how proposals are shown (see docs/ROADMAP.md).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from brain_core.changes import EXTERNAL_VIA, Proposal, data_dir

Decision = Literal["approved", "edited", "rejected"]
# Above this share of "approved as is", the review is probably a formality.
RUBBER_STAMP = 0.9

_lock = threading.Lock()


def log_file() -> Path:
    return data_dir() / "approvals.jsonl"


def record(proposal: Proposal, decision: Decision, *, batch: bool = False) -> None:
    """Append one decision. Best effort: the decision itself already happened."""
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "id": proposal.id,
        "agent": proposal.agent,
        "via": proposal.via,
        "approval": proposal.approval,
        "decision": decision,
        "batch": batch,
    }
    try:
        path = log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def decision_for(proposal: Proposal) -> Decision:
    return "edited" if proposal.edited else "approved"


def summary(days: int = 30, now: datetime | None = None) -> dict[str, Any]:
    """Counts for the last ``days`` days, overall and for outside material."""
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    try:
        lines = log_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
            at = datetime.fromisoformat(e["at"])
        except (ValueError, KeyError, TypeError):
            continue
        if at >= since:
            rows.append(e)

    def counts(subset: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(subset)
        out: dict[str, Any] = {
            "total": total,
            "approved": sum(1 for e in subset if e.get("decision") == "approved"),
            "edited": sum(1 for e in subset if e.get("decision") == "edited"),
            "rejected": sum(1 for e in subset if e.get("decision") == "rejected"),
            "batch": sum(1 for e in subset if e.get("batch")),
        }
        out["approved_rate"] = round(out["approved"] / total, 3) if total else None
        return out

    overall = counts(rows)
    external = counts([e for e in rows if e.get("via") in EXTERNAL_VIA])
    rate = overall["approved_rate"]
    return {
        "days": days,
        **overall,
        "external": external,
        # Only meaningful once there is enough to judge.
        "rubber_stamp": bool(rate is not None and overall["total"] >= 20 and rate >= RUBBER_STAMP),
        "threshold": RUBBER_STAMP,
    }
