"""Opt-in compatibility tests against a REAL Wooju Brain.

These do not run by default (no real Brain is assumed in CI). Point the
``WOOJU_REAL_BRAIN`` env var at a Brain directory to exercise them:

    WOOJU_REAL_BRAIN=/path/to/wooju-brain uv run pytest tests/test_real_brain.py

They validate the Phase 4 acceptance criteria against representative content:
derived insights (origin: synthesis) with a lifecycle status, an insight kind,
and ``derived_from`` that uses the Brain's mixed ``[[wikilink]]`` /
``[label](path.md)`` forms — without altering the real Brain in any way.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from brain_core.index import BrainIndex

_REAL_RAW = os.environ.get("WOOJU_REAL_BRAIN", "").strip()
REAL = Path(_REAL_RAW).expanduser() if _REAL_RAW else None
pytestmark = pytest.mark.skipif(
    REAL is None or not REAL.is_dir(),
    reason="set WOOJU_REAL_BRAIN to a real Brain directory to run real-Brain tests",
)


@pytest.fixture(scope="module")
def index() -> BrainIndex:
    idx = BrainIndex()
    idx.scan(REAL)
    return idx


def test_real_brain_has_known_categories(index):
    cats = index.stats()["by_category"]
    # A representative Brain has knowledge, sources, and at least one insight.
    assert cats.get("knowledge", 0) > 0
    assert cats.get("source", 0) > 0
    assert cats.get("insight", 0) >= 1


def test_real_insight_has_status_kind_and_derivation(index):
    """At least one real derived insight with status, kind, and derived_from."""
    insights = index.insights()
    assert insights, "expected at least one origin: synthesis insight"
    sample = next(i for i in insights if i.derived_from)
    assert sample.kind in {"pattern", "tension", "connection"} or sample.kind is not None
    # Lifecycle status is read verbatim and established is never inferred.
    assert sample.status in {"candidate", "provisional", "established"}
    # At least one derivation ref resolves to a real record (derivation, not proof).
    resolved = [r for r in sample.derived_from_resolved if r.resolved_id]
    assert resolved, "expected at least one resolvable derived_from ref"
    assert all(r.title for r in resolved)  # resolved refs carry a readable title


def test_real_brain_mixed_derived_from_forms_resolve(index):
    """The Brain's [[x]] and [label](path.md) derived_from forms both resolve."""
    resolved_by_form = {"wikilink": 0, "mdlink": 0}
    for rec in index.insights():
        for ref in rec.derived_from_resolved:
            if not ref.resolved_id:
                continue
            if ref.ref.startswith("[["):
                resolved_by_form["wikilink"] += 1
            elif ref.ref.startswith("["):
                resolved_by_form["mdlink"] += 1
    assert resolved_by_form["wikilink"] > 0
    assert resolved_by_form["mdlink"] > 0


def test_real_brain_source_subtype_and_no_epistemic_status(index):
    """Sources surface source_type as subtype and carry no epistemic status."""
    sources = index.sources()
    assert sources
    assert any(s.subtype == "paper" for s in sources)
    assert all(s.status is None for s in sources)  # availability status is not epistemic


def test_real_brain_not_mutated(index):
    """Scanning the real Brain changes nothing on disk."""
    # Re-scan and confirm mtimes/contents are stable for a sample of files.
    md_files = sorted(REAL.rglob("*.md"))
    assert md_files
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in md_files[:5]}
    index.scan(REAL)  # rescan
    for p, (data, mtime) in before.items():
        assert p.read_bytes() == data
        assert p.stat().st_mtime_ns == mtime


# ----------------------------------------------------------- Phase 4 attention


def test_real_attention_surfaces_active_insights(index):
    """At least one provisional/candidate insight is surfaced (current uncertainty)."""
    from app.projections.attention import compute_attention

    resp = compute_attention(index)
    keys = {g.key for g in resp.groups}
    surfaced = {i.id for g in resp.groups for i in g.items}
    # The real Brain's derived insights are candidate/provisional — never established-only.
    assert surfaced, "expected the real Brain to have at least one attention item"
    assert {"provisional", "candidate"} & keys


def test_real_attention_items_reference_real_records(index):
    """Every surfaced attention item must resolve to a real record id."""
    from app.projections.attention import compute_attention

    resp = compute_attention(index)
    ids = {i.id for g in resp.groups for i in g.items}
    assert ids
    assert ids <= set(index.records.keys())


def test_real_attention_is_read_only(index):
    """Computing attention changes nothing on disk."""
    from app.projections.attention import compute_attention

    md_files = sorted(REAL.rglob("*.md"))
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in md_files[:5]}
    compute_attention(index)
    for p, (data, mtime) in before.items():
        assert p.read_bytes() == data
        assert p.stat().st_mtime_ns == mtime
