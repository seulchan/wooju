from __future__ import annotations

import pytest

from brain_core import history


def test_ensure_repo_commits_existing_files(make_brain):
    brain = make_brain({"wiki/concepts/a.md": "# A"})
    history.ensure_repo(brain)
    entries = history.log(brain)
    assert [e.title for e in entries] == ["Start this Brain"]
    assert entries[0].paths == ("wiki/concepts/a.md",)


def test_commit_only_touches_given_paths(make_brain):
    brain = make_brain({"a.md": "1", "b.md": "1"})
    history.ensure_repo(brain)
    (brain / "a.md").write_text("2")
    (brain / "b.md").write_text("user edit in another app")
    history.commit_paths(brain, ["a.md"], "Change a")
    assert history.log(brain)[0].paths == ("a.md",)


def test_delete_is_recorded_and_undo_restores(make_brain):
    brain = make_brain({"inbox/x.md": "raw"})
    history.ensure_repo(brain)
    (brain / "inbox/x.md").unlink()
    sha = history.commit_paths(brain, ["inbox/x.md"], "Process x")
    history.undo(brain, sha)
    assert (brain / "inbox/x.md").read_text() == "raw"
    top = history.log(brain)[0]
    assert top.title == "Undo: Process x" and top.undoes == sha


def test_undo_refuses_when_file_changed_later(make_brain):
    brain = make_brain({"a.md": "1"})
    history.ensure_repo(brain)
    (brain / "a.md").write_text("2")
    sha = history.commit_paths(brain, ["a.md"], "Change a")
    (brain / "a.md").write_text("3")
    with pytest.raises(history.HistoryError):
        history.undo(brain, sha)
    assert (brain / "a.md").read_text() == "3"


def test_first_commit_cannot_be_undone(make_brain):
    brain = make_brain({"a.md": "1"})
    history.ensure_repo(brain)
    with pytest.raises(history.HistoryError):
        history.undo(brain, history.log(brain)[0].id)


def test_log_without_repo_is_empty(make_brain):
    assert history.log(make_brain({})) == []
