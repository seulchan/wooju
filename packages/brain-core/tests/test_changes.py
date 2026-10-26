from __future__ import annotations

import pytest

from brain_core import history
from brain_core.changes import (
    FileChange,
    Proposal,
    ProposalError,
    ProposalStore,
    apply_proposal,
    approval_for,
    reject_proposal,
)

SOURCE = """---
title: T
source_type: article
canonical_ref: "https://example.com"
published: 2026
accessed: 2026-10-26
---
## 한 줄 요약

내용.
"""


def make(changes, **kw):
    return Proposal(agent="test", title="Test", changes=changes, **kw)


def test_approval_levels():
    assert approval_for([FileChange(op="write", path="sources/a.md", content="x")]) == "auto"
    assert approval_for([FileChange(op="delete", path="inbox/a.pdf")]) == "auto"
    assert approval_for([FileChange(op="write", path="wiki/concepts/a.md", content="x")]) == "batch"
    assert (
        approval_for([FileChange(op="write", path="memory/records/a.md", content="x")])
        == "individual"
    )
    promoted = "---\norigin: synthesis\nstatus: provisional\n---\n"
    assert (
        approval_for([FileChange(op="write", path="wiki/questions/a.md", content=promoted)])
        == "individual"
    )
    candidate = "---\norigin: synthesis\nstatus: candidate\n---\n"
    assert (
        approval_for([FileChange(op="write", path="wiki/questions/a.md", content=candidate)])
        == "batch"
    )


@pytest.mark.parametrize(
    "path",
    ["../x.md", "/etc/x", ".git/config", "docs/AGENTS.md", "AGENTS.md", "sources/.hidden.md"],
)
def test_unsafe_paths_are_refused(path):
    with pytest.raises(ProposalError):
        approval_for([FileChange(op="write", path=path, content="x")])


def test_apply_writes_copies_deletes_and_commits(make_brain):
    brain = make_brain({"inbox/report.txt": "original"})
    p = make(
        [
            FileChange(op="write", path="sources/report.md", content=SOURCE),
            FileChange(op="copy", path="library/report.txt", source="inbox/report.txt"),
            FileChange(op="delete", path="inbox/report.txt"),
        ],
        origin="inbox/report.txt",
    )
    result = apply_proposal(brain, p)
    assert result.status == "applied", result.error
    assert (brain / "library/report.txt").read_text() == "original"
    assert not (brain / "inbox/report.txt").exists()
    top = history.log(brain)[0]
    assert top.id == result.commit
    assert set(top.paths) == {"sources/report.md", "library/report.txt", "inbox/report.txt"}
    assert f"Proposal: {p.id}" in top.message


def test_change_that_adds_errors_is_rolled_back(make_brain):
    brain = make_brain({"sources/ok.md": SOURCE})
    history.ensure_repo(brain)
    bad = make(
        [FileChange(op="write", path="sources/bad.md", content="---\ntitle: no type\n---\n")]
    )
    result = apply_proposal(brain, bad)
    assert result.status == "failed"
    assert "source_type" in (result.error or "")
    assert not (brain / "sources/bad.md").exists()
    assert len(history.log(brain)) == 1


def test_existing_errors_do_not_block_unrelated_changes(make_brain):
    brain = make_brain({"sources/old.md": "---\ntitle: broken\n---\n"})
    result = apply_proposal(
        brain, make([FileChange(op="write", path="sources/new.md", content=SOURCE)])
    )
    assert result.status == "applied", result.error


def test_failed_overwrite_restores_previous_content(make_brain):
    brain = make_brain({"sources/a.md": SOURCE})
    history.ensure_repo(brain)
    result = apply_proposal(
        brain, make([FileChange(op="write", path="sources/a.md", content="---\nx: 1\n---\n")])
    )
    assert result.status == "failed"
    assert (brain / "sources/a.md").read_text() == SOURCE


def test_applied_change_can_be_undone(make_brain):
    brain = make_brain({})
    result = apply_proposal(
        brain, make([FileChange(op="write", path="sources/a.md", content=SOURCE)])
    )
    history.undo(brain, result.commit)
    assert not (brain / "sources/a.md").exists()


def test_store_round_trip_and_reject(tmp_path):
    store = ProposalStore(tmp_path)
    p = store.save(make([FileChange(op="write", path="sources/a.md", content="x")]))
    assert store.get(p.id).title == "Test"
    assert [x.id for x in store.list("pending")] == [p.id]
    reject_proposal(p, store)
    assert store.get(p.id).status == "rejected"
    assert store.list("pending") == []
    assert store.get("../../etc") is None
    with pytest.raises(ProposalError):
        reject_proposal(p, store)


def test_undo_keeps_a_note_edited_outside_wooju(tmp_path):
    """A note the user wrote or edited elsewhere survives undoing a later proposal."""
    from brain_core import history
    from brain_core.changes import FileChange, Proposal, apply_proposal

    history.ensure_repo(tmp_path)
    note = tmp_path / "wiki" / "concepts" / "mine.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\ntitle: 내 노트\n---\n# 내 노트\n\n직접 쓴 글\n", encoding="utf-8")

    p = apply_proposal(
        tmp_path,
        Proposal(
            agent="test",
            title="Edit",
            changes=[
                FileChange(
                    op="write",
                    path="wiki/concepts/mine.md",
                    content="---\ntitle: 내 노트\nreview_after: 2027-01-01\n---\n# 내 노트\n\n직접 쓴 글\n",
                )
            ],
            approval="batch",
        ),
    )
    assert p.status == "applied"
    history.undo(tmp_path, p.commit)
    assert note.read_text(encoding="utf-8").endswith("직접 쓴 글\n")
    assert "review_after" not in note.read_text(encoding="utf-8")
