"""Challenger agent: test an insight against the rest of the Brain.

An insight (``origin: synthesis``) is a derived idea, not a fact. Before it is
promoted past ``candidate`` it needs a ``## Challenge`` section (SYNTHESIS.md).
The Challenger reads the insight, the notes it was derived from, and other
passages that may bear on it, and proposes that section: what would make it
wrong, counter-evidence (cited as links), scope limits, stale or missing
support, and a verdict.

The proposal only adds text. It never changes ``status``: promoting or
rejecting an insight stays the user's decision. An existing Challenge section
is kept, and the new result is added under it with the date.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

from brain_core.changes import FileChange, Proposal, approval_for
from brain_core.index import BrainIndex
from brain_core.messages import UserFacingError
from brain_core.retrieve import Passage, Retriever, passages

from .llm import Provider
from .text import normalize_korean

AGENT = "challenger"
MAX_PASSAGES = 10
_LANGUAGE_NAME = {"ko": "Korean", "en": "English"}

Verdict = Literal["reject", "refine", "keep_candidate", "ready_for_provisional"]


class ChallengeError(UserFacingError):
    """The note cannot be challenged; ``key`` names the user message."""


class ChallengeDraft(BaseModel):
    wrong_if: Annotated[list[str], Field(min_length=1, max_length=4)] = Field(
        description="Concrete conditions or facts that would make the insight wrong."
    )
    counter_evidence: Annotated[list[str], Field(max_length=4)] = Field(
        default_factory=list,
        description="Passages that contradict or weaken it, each citing [n]. Empty if none.",
    )
    scope_limits: Annotated[list[str], Field(max_length=3)] = Field(
        default_factory=list, description="Where it overreaches, generalizes, or relies on analogy."
    )
    stale_or_missing: Annotated[list[str], Field(max_length=3)] = Field(
        default_factory=list,
        description="Support that is old, superseded, or absent from the passages.",
    )
    restatement: bool = Field(
        description="True if the insight only repeats what one source already says."
    )
    verdict: Verdict
    reason: str = Field(description="One sentence explaining the verdict.")


_SYSTEM = (
    "You are a skeptical reviewer of investment-research hypotheses in a personal notebook. "
    "Try to break the insight. Use only the numbered passages and general reasoning about "
    "logic and scope; do not invent facts, figures, or events. Cite passages as [n]. "
    "Verdicts: reject = unsupported, wrong, or redundant; refine = worth keeping but the claim "
    "must be narrowed or fixed; keep_candidate = plausible but untested; "
    "ready_for_provisional = it survives this challenge, though support may be incomplete. "
    "Be concise and specific. Write all text in {language}."
)

_LABELS = {
    "ko": {
        "wrong_if": "무엇이 이것을 틀리게 만드나",
        "counter": "반대 근거",
        "scope": "범위와 과장 위험",
        "stale": "오래되었거나 빠진 근거",
        "restatement": "새로운가: 자료 하나를 다시 말한 것에 가까워요.",
        "verdict": "판정",
        "by": "Challenger 검토",
        "verdicts": {
            "reject": "기각 권고",
            "refine": "보완 필요",
            "keep_candidate": "후보로 유지",
            "ready_for_provisional": "잠정(provisional)으로 올릴 만함",
        },
    },
    "en": {
        "wrong_if": "What would make this wrong",
        "counter": "Counterexamples or contradictions",
        "scope": "Scope limits, analogy risks, or overreach",
        "stale": "Stale or missing support",
        "restatement": "Genuinely new? It mostly restates one source.",
        "verdict": "Verdict",
        "by": "Challenger review",
        "verdicts": {
            "reject": "reject",
            "refine": "refine",
            "keep_candidate": "keep as candidate",
            "ready_for_provisional": "ready for provisional",
        },
    },
}


def evidence(index: BrainIndex, insight_id: str, retriever: Retriever) -> list[Passage]:
    """The insight's own sources first, then other passages that may bear on it."""
    record = index.get(insight_id)
    assert record is not None
    found: list[Passage] = []
    for ref in record.derived_from_resolved:
        target = index.get(ref.resolved_id) if ref.resolved_id else None
        if target is not None:
            found.extend(passages(target)[:2])
    query = f"{record.title} {_section(record.content, 'Insight') or ''}"
    seen = {(p.id, p.heading) for p in found}
    for _, p in retriever.search(query, limit=MAX_PASSAGES * 2):
        if p.id == insight_id or (p.id, p.heading) in seen:
            continue
        found.append(p)
        seen.add((p.id, p.heading))
        if len(found) >= MAX_PASSAGES:
            break
    return found[:MAX_PASSAGES]


def _section(body: str, title: str) -> str | None:
    m = re.search(rf"^##\s+{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", body, re.M | re.S | re.I)
    return m.group(1).strip() if m else None


def _link(from_path: str, target: Passage) -> str:
    rel = os.path.relpath(target.record.path, os.path.dirname(from_path) or ".")
    return f"[{target.record.title}]({PurePosixPath(rel).as_posix()})"


def _cite_links(text: str, from_path: str, found: list[Passage]) -> str:
    def repl(m: re.Match[str]) -> str:
        links = []
        for n in re.findall(r"\d+", m.group(0)):
            i = int(n)
            if 1 <= i <= len(found):
                links.append(_link(from_path, found[i - 1]))
        return f"({', '.join(dict.fromkeys(links))})" if links else ""

    out = re.sub(r"\[\s*\d+(?:\s*[,，]\s*\d+)*\s*\]", repl, text)
    return re.sub(r"\s+([.,。])", r"\1", out).strip()


def render_challenge(
    draft: ChallengeDraft, *, path: str, found: list[Passage], language: str, today: date
) -> list[str]:
    """Bullet lines for the Challenge section (without the heading)."""
    labels = _LABELS.get(language, _LABELS["en"])
    fix = normalize_korean if language == "ko" else (lambda s: s)

    def items(values: list[str]) -> str:
        cleaned = [fix(_cite_links(v.strip(), path, found)) for v in values if v.strip()]
        return "; ".join(cleaned)

    lines = []
    for key, values in (
        ("wrong_if", draft.wrong_if),
        ("counter", draft.counter_evidence),
        ("scope", draft.scope_limits),
        ("stale", draft.stale_or_missing),
    ):
        text = items(values)
        if text:
            lines.append(f"- {labels[key]}: {text}")
    if draft.restatement:
        lines.append(f"- {labels['restatement']}")
    verdict = labels["verdicts"][draft.verdict]
    lines.append(
        f"- {labels['verdict']} ({labels['by']}, {today.isoformat()}): {verdict}. "
        f"{fix(_cite_links(draft.reason.strip(), path, found))}"
    )
    return lines


def insert_challenge(text: str, lines: list[str], *, heading_note: str) -> str:
    """Add the lines as the Challenge section, or under an existing one."""
    block = "\n".join(lines)
    existing = re.search(r"^##\s+Challenge\s*$", text, re.M | re.I)
    if existing:
        nxt = re.search(r"^##\s", text[existing.end() :], re.M)
        end = existing.end() + nxt.start() if nxt else len(text)
        before, after = text[:end].rstrip("\n"), text[end:]
        return f"{before}\n\n### {heading_note}\n\n{block}\n\n{after.lstrip()}".rstrip() + "\n"
    for anchor in ("Assessment", "Destination and Use"):
        m = re.search(rf"^##\s+{anchor}\s*$", text, re.M | re.I)
        if m:
            return f"{text[: m.start()]}## Challenge\n\n{block}\n\n{text[m.start() :]}"
    return text.rstrip("\n") + f"\n\n## Challenge\n\n{block}\n"


def challenge_insight(
    brain_root,  # noqa: ANN001 — Path; kept loose for tests
    index: BrainIndex,
    insight_id: str,
    provider: Provider,
    *,
    language: str,
    retriever: Retriever | None = None,
    today: date | None = None,
) -> Proposal:
    record = index.get(insight_id)
    if record is None:
        raise ChallengeError(insight_id, "challenge.not_found")
    if record.category != "insight":
        raise ChallengeError(insight_id, "challenge.not_insight")
    today = today or date.today()
    retriever = retriever or Retriever(index)
    found = evidence(index, insight_id, retriever)

    blocks = [
        f"[{n}] {p.record.title}{f' — {p.heading}' if p.heading else ''} "
        f"({p.record.category})\n{p.text.strip()}"
        for n, p in enumerate(found, 1)
    ]
    user = (
        f"Insight ({record.status or 'candidate'}, {record.kind or 'insight'}):\n"
        f"# {record.title}\n\n{record.content.strip()}\n\n"
        "Passages from the notebook:\n\n" + ("\n\n".join(blocks) or "(none)")
    )
    system = _SYSTEM.format(language=_LANGUAGE_NAME.get(language, "English"))
    result = provider.generate_json(system, user, ChallengeDraft.model_json_schema())
    try:
        draft = ChallengeDraft.model_validate(result.data)
    except ValidationError as exc:
        raise ChallengeError(str(exc), "challenge.bad_shape") from exc

    path = record.path
    original = (brain_root / path).read_text(encoding="utf-8")
    lines = render_challenge(draft, path=path, found=found, language=language, today=today)
    labels = _LABELS.get(language, _LABELS["en"])
    updated = insert_challenge(original, lines, heading_note=f"{labels['by']} {today.isoformat()}")
    changes = [FileChange(op="write", path=path, content=updated)]
    verdict = labels["verdicts"][draft.verdict]
    title = f"반론 검토: {record.title}" if language == "ko" else f"Challenge: {record.title}"
    return Proposal(
        agent=AGENT,
        origin=path,
        title=title,
        summary=f"{verdict}. {draft.reason.strip()}",
        changes=changes,
        approval=approval_for(changes),
    )
