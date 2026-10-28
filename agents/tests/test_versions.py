from __future__ import annotations

from datetime import date

from wooju_agents import versions

OLD = (
    "The index has 100 constituents. Companies were picked on profitability. "
    "Futures start trading in November."
)


def test_small_page_noise_is_not_a_new_version():
    changes = versions.compare(OLD, OLD.replace("November", "December"))
    assert not changes.significant


def test_added_and_removed_sentences_are_found_in_order():
    new = (
        "The index has 100 constituents. Ten companies were added after a review of "
        "shareholder returns in the second quarter of the year. Futures start trading in "
        "November. The rebalancing takes effect in December, the committee said on Monday."
    )
    changes = versions.compare(OLD, new)
    assert changes.significant
    assert changes.removed == ["Companies were picked on profitability."]
    assert changes.added[0].startswith("Ten companies were added")
    assert changes.added[-1].startswith("The rebalancing takes effect")


def test_the_section_and_the_retired_earlier_note():
    changes = versions.Changes(added=["New [x] fact. " * 3], removed=["Old fact."])
    block = versions.section(
        changes, earlier_title="Index", earlier_link="../sources/index.md", language="en"
    )
    assert "## What changed since the earlier version" in block
    assert "- Earlier version: [Index](../sources/index.md)" in block
    assert "  > New \\[x] fact." in block and "  > Old fact." in block
    note = "---\ntitle: T\n---\n# T\n\n## Key Ideas\n\n- a\n\n## Original\n\n- [x](y)\n"
    out = versions.add_section(note, block)
    assert out.index("## What changed") < out.index("## Original")
    earlier = "---\ntitle: T\nstatus: active\n---\n# T\n"
    retired = versions.retire_earlier(
        earlier, new_path="sources/t-2.md", today=date(2026, 10, 28), language="en"
    )
    assert "superseded_by: sources/t-2.md" in retired and "status: archived" in retired
    assert "status_before_retired: active" in retired and "retired: 2026-10-28" in retired
