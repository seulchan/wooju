"""Tests for BrainIndex: scanning, classification, resolution, search, isolation."""

from __future__ import annotations

import os

from brain_core.index import BrainIndex

# ----------------------------------------------------------------- scanning


def test_empty_brain(make_brain):
    brain = make_brain({})
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.records == {}
    assert idx.stats()["total"] == 0
    assert idx.search("anything") == []
    assert idx.recent() == []


def test_published_records_cannot_be_mutated_outside_a_scan(make_brain):
    brain = make_brain({"wiki/a.md": "# A"})
    idx = BrainIndex()
    idx.scan(brain)

    try:
        idx.records["wiki/b"] = idx.get("wiki/a")  # type: ignore[index]
    except TypeError:
        pass
    else:  # pragma: no cover - MappingProxyType should always reject assignment
        raise AssertionError("published catalog mapping unexpectedly accepted mutation")

    assert idx.get("wiki/b") is None


def test_markdown_without_frontmatter(make_brain):
    brain = make_brain({"wiki/plain.md": "# Plain Note\n\nNo frontmatter here."})
    idx = BrainIndex()
    idx.scan(brain)
    rec = idx.get("wiki/plain")
    assert rec is not None
    assert rec.metadata == {}
    assert rec.title == "Plain Note"  # from H1
    assert rec.category == "knowledge"


def test_markdown_with_frontmatter(make_brain):
    brain = make_brain({"wiki/x.md": "---\ntitle: T\naliases: [A1]\n---\nbody"})
    idx = BrainIndex()
    idx.scan(brain)
    rec = idx.get("wiki/x")
    assert rec is not None
    assert rec.metadata["title"] == "T"
    assert rec.aliases == ["A1"]
    assert rec.content == "body"


# ------------------------------------------------------------ classification


def test_classification_by_directory(make_brain):
    brain = make_brain(
        {
            "wiki/k.md": "# K",
            "sources/s.md": "# S",
            "library/l.md": "# L",
            "memory/m.md": "# M",
            "projects/p.md": "# P",
            "areas/a.md": "# A",
            "misc/o.md": "# O",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    by_id = {rid: r.category for rid, r in idx.records.items()}
    assert by_id["wiki/k"] == "knowledge"
    assert by_id["sources/s"] == "source"
    assert by_id["library/l"] == "source"
    assert by_id["memory/m"] == "memory"
    assert by_id["projects/p"] == "project"
    assert by_id["areas/a"] == "area"
    assert by_id["misc/o"] == "other"


def test_insight_metadata_overrides_location(make_brain):
    # A wiki note marked as synthesis becomes an insight, leaving knowledge.
    brain = make_brain(
        {
            "wiki/insight.md": (
                "---\norigin: synthesis\nkind: pattern\nstatus: provisional\n"
                'derived_from: "[[wiki/k]]"\n---\n# Pattern\n'
            ),
            "wiki/k.md": "# K",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    insight = idx.get("wiki/insight")
    assert insight is not None
    assert insight.category == "insight"
    assert insight.kind == "pattern"
    # Excluded from knowledge listing.
    assert all(r.id != "wiki/insight" for r in idx.knowledge())
    assert insight in idx.insights()


def test_status_preservation_and_no_inference(make_brain):
    brain = make_brain(
        {
            "wiki/cand.md": "---\norigin: synthesis\nstatus: candidate\n---\n",
            "wiki/prov.md": "---\norigin: synthesis\nstatus: provisional\n---\n",
            "wiki/est.md": "---\norigin: synthesis\nstatus: established\n---\n",
            "wiki/nostatus.md": "---\norigin: synthesis\n---\n",  # status absent
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/cand").status == "candidate"
    assert idx.get("wiki/prov").status == "provisional"
    assert idx.get("wiki/est").status == "established"
    # Missing status stays None — established is NEVER inferred.
    assert idx.get("wiki/nostatus").status is None


def test_subtype_and_kind_from_frontmatter(make_brain):
    brain = make_brain(
        {
            "wiki/q.md": "---\ntype: question\n---\n",
            "wiki/howto.md": "---\ntype: how-to\n---\n",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/q").subtype == "question"
    assert idx.get("wiki/howto").subtype == "how-to"
    # subtype filter works
    ids = {r.id for r in idx.knowledge(subtype="question")}
    assert ids == {"wiki/q"}


def test_real_brain_metadata_conventions(make_brain):
    """The Brain uses insight_kind/source_type; classify must read them."""
    brain = make_brain(
        {
            "wiki/mental-models/m.md": (
                "---\norigin: synthesis\ninsight_kind: tension\nstatus: provisional\n---\n"
            ),
            "sources/paper.md": "---\nsource_type: paper\nstatus: active\n---\n",
            "library/book.md": "---\nsource_type: book\n---\n",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    insight = idx.get("wiki/mental-models/m")
    assert insight.category == "insight"
    assert insight.kind == "tension"  # insight_kind, not kind
    assert insight.status == "provisional"

    paper = idx.get("sources/paper")
    assert paper.category == "source"
    assert paper.subtype == "paper"  # source_type surfaced as subtype
    # A source's availability `status` is NOT an epistemic status.
    assert paper.status is None
    assert paper.metadata.get("status") == "active"  # preserved in raw metadata


def test_status_only_applies_to_insights(make_brain):
    """Top-level status is the insight lifecycle; non-insights keep status=None."""
    brain = make_brain(
        {
            "wiki/k.md": "---\nstatus: provisional\n---\n# K",  # knowledge, not insight
            "sources/s.md": "---\nstatus: active\n---\n",  # source availability
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/k").status is None  # not an insight -> not epistemic
    assert idx.get("sources/s").status is None
    # by_status counts only insight lifecycle statuses -> empty here.
    assert idx.stats()["by_status"] == {}


def test_hidden_directories_are_pruned(make_brain):
    brain = make_brain(
        {
            "wiki/real.md": "# Real",
            ".obsidian/config.md": "# config",
            ".agents/skills/x/SKILL.md": "# skill",
            ".hidden/note.md": "# hidden",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/real") is not None
    assert idx.stats()["total"] == 1  # only the non-hidden note


def test_indexed_at_advances_on_each_scan(make_brain):
    import time

    brain = make_brain({"wiki/a.md": "# A"})
    idx = BrainIndex()
    assert idx.indexed_at is None
    idx.scan(brain)
    first = idx.indexed_at
    assert first is not None
    time.sleep(0.001)  # ensure the timestamp can move (microsecond resolution)
    idx.scan(brain)
    assert idx.indexed_at is not None
    assert idx.indexed_at != first
    assert idx.stats()["indexed_at"] == idx.indexed_at


# ------------------------------------------------------------- wikilinks


def test_resolved_wikilink(make_brain):
    brain = make_brain(
        {
            "wiki/index.md": "See [[llm-agent-memory]] for more.",
            "wiki/llm-agent-memory.md": "# Agent Memory",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    links = idx.get("wiki/index").links
    assert len(links) == 1
    assert links[0].target == "llm-agent-memory"
    assert links[0].resolved_id == "wiki/llm-agent-memory"


def test_unresolved_wikilink_preserved(make_brain):
    brain = make_brain({"wiki/index.md": "See [[does-not-exist]]."})
    idx = BrainIndex()
    idx.scan(brain)
    links = idx.get("wiki/index").links
    assert len(links) == 1
    assert links[0].target == "does-not-exist"
    assert links[0].resolved_id is None  # preserved but unresolved


def test_ambiguous_wikilink_resolves_deterministically(make_brain):
    # Two records share the "memory" basename in different dirs.
    brain = make_brain(
        {
            "wiki/index.md": "[[memory]]",
            "wiki/memory.md": "# M1",
            "sources/memory.md": "# M2",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    resolved = idx.get("wiki/index").links[0].resolved_id
    # Both have one path segment; lexical tiebreak -> "sources/memory".
    assert resolved == "sources/memory"


# ------------------------------------------------------------- derived_from


def test_derived_from_raw_and_resolved(make_brain):
    brain = make_brain(
        {
            "wiki/insight.md": (
                "---\norigin: synthesis\nstatus: provisional\n"
                'derived_from:\n  - wiki/k\n  - "[[missing]]"\n---\n'
            ),
            "wiki/k.md": "# K",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    insight = idx.get("wiki/insight")
    assert insight.derived_from == ["wiki/k", "[[missing]]"]
    resolved = {r.ref: r.resolved_id for r in insight.derived_from_resolved}
    assert resolved["wiki/k"] == "wiki/k"
    assert resolved["[[missing]]"] is None  # derivation provenance, not proof


def test_derived_from_mixed_forms_resolve_with_title(make_brain):
    """The Brain writes derived_from as [[x]], [label](path.md), and bare ids."""
    brain = make_brain(
        {
            "wiki/insight.md": (
                "---\norigin: synthesis\nstatus: provisional\n"
                "derived_from:\n"
                '  - "[[concepts/foo]]"\n'
                '  - "[Generative Agents](../../sources/gen.md)"\n'
                "  - wiki/concepts/foo\n"
                "---\n"
            ),
            "wiki/concepts/foo.md": "---\ntitle: Foo Concept\n---\n",
            "sources/gen.md": "---\ntitle: Generative Agents\n---\n",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    insight = idx.get("wiki/insight")
    by_ref = {r.ref: r for r in insight.derived_from_resolved}
    # Wikilink form resolves by suffix match; title carried for readable links.
    assert by_ref["[[concepts/foo]]"].resolved_id == "wiki/concepts/foo"
    assert by_ref["[[concepts/foo]]"].title == "Foo Concept"
    # Markdown-link form: relative path + .md stripped, then resolved.
    assert by_ref["[Generative Agents](../../sources/gen.md)"].resolved_id == "sources/gen"
    assert by_ref["[Generative Agents](../../sources/gen.md)"].title == "Generative Agents"
    # Bare id resolves exactly.
    assert by_ref["wiki/concepts/foo"].resolved_id == "wiki/concepts/foo"


# ------------------------------------------------------------- search


def test_search_matches_and_ranks_deterministically(make_brain):
    # Equal mtimes so ranking is decided purely by score, then path asc.
    brain = make_brain(
        {
            "wiki/a.md": "---\ntitle: Alpha Beta\n---\nbeta in body",
            "wiki/b.md": "---\ntitle: Other\n---\nalpha beta gamma",
            "wiki/c.md": "---\ntitle: Beta\n---\nnothing relevant",
        },
        mtimes={"wiki/a.md": 1_000_000, "wiki/b.md": 1_000_000, "wiki/c.md": 1_000_000},
    )
    idx = BrainIndex()
    idx.scan(brain)
    # "beta" matches all three: a & c in title (score 100), b in body (score 10).
    scored = idx.search("beta")
    ids = [r.id for _, r in scored]
    # Score desc (a,c before b); equal-score tiebreak is path asc (a before c).
    assert ids == ["wiki/a", "wiki/c", "wiki/b"]


def test_search_requires_all_terms_and_blank_is_empty(make_brain):
    brain = make_brain({"wiki/a.md": "alpha beta"})
    idx = BrainIndex()
    idx.scan(brain)
    assert len(idx.search("alpha beta")) == 1
    assert idx.search("alpha zeta") == []  # zeta absent -> no match
    assert idx.search("") == []  # blank query -> no results
    assert idx.search("   ") == []


# ------------------------------------------------------------- isolation


def test_malformed_file_isolation(make_brain):
    # A non-UTF-8 file is skipped; its sibling is still indexed.
    brain = make_brain({"wiki/good.md": "# Good"})
    (brain / "wiki" / "bad.md").write_bytes(b"\xff\xfe\x00\x01 not valid utf-8")
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/good") is not None
    assert idx.get("wiki/bad") is None
    assert idx.stats()["total"] == 1


def test_symlink_is_skipped(make_brain):
    brain = make_brain({"wiki/real.md": "# Real"})
    link = brain / "wiki" / "linked.md"
    os.symlink(brain / "wiki" / "real.md", link)
    idx = BrainIndex()
    idx.scan(brain)
    assert idx.get("wiki/real") is not None
    assert idx.get("wiki/linked") is None  # symlink never followed


# ------------------------------------------------------------- determinism


def test_recent_orders_by_modified_at_desc(make_brain):
    brain = make_brain(
        {"wiki/old.md": "# Old", "wiki/mid.md": "# Mid", "wiki/new.md": "# New"},
        mtimes={"wiki/old.md": 1_000_000, "wiki/mid.md": 2_000_000, "wiki/new.md": 3_000_000},
    )
    idx = BrainIndex()
    idx.scan(brain)
    order = [r.id for r in idx.recent()]
    assert order == ["wiki/new", "wiki/mid", "wiki/old"]


def test_stats_counts(make_brain):
    brain = make_brain(
        {
            "wiki/k.md": "# K",
            "wiki/i.md": "---\norigin: synthesis\nstatus: provisional\n---\n",
            "sources/s.md": "# S",
        }
    )
    idx = BrainIndex()
    idx.scan(brain)
    stats = idx.stats()
    assert stats["total"] == 3
    assert stats["by_category"]["knowledge"] == 1
    assert stats["by_category"]["insight"] == 1
    assert stats["by_category"]["source"] == 1
    assert stats["by_status"]["provisional"] == 1
