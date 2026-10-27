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


def test_no_empty_commits(make_brain):
    brain = make_brain({"a.md": "1"})
    history.ensure_repo(brain)
    head = history.log(brain)[0].id
    assert history.commit_paths(brain, ["a.md"], "Nothing changed") == head
    assert len(history.log(brain)) == 1


def test_history_lives_outside_icloud_sync(tmp_path):
    """New Brains keep git objects in a .nosync folder; old .git folders are moved."""
    import subprocess

    from brain_core.history import HISTORY_DIR, commit_paths, ensure_repo, is_repo, log

    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    ensure_repo(tmp_path)
    assert (tmp_path / ".git").is_file() and (tmp_path / HISTORY_DIR).is_dir()
    assert (tmp_path / ".git").read_text() == f"gitdir: {HISTORY_DIR}\n"
    (tmp_path / "b.md").write_text("y", encoding="utf-8")
    commit_paths(tmp_path, ["b.md"], "Add b")
    assert [e.title for e in log(tmp_path)][:2] == ["Add b", "Start this Brain"]
    # Plain git agrees, and the history folder itself is not reported as untracked.
    status = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--short"], capture_output=True, text=True
    ).stdout
    assert status.strip() == ""

    # An existing Brain with a .git folder (made by an earlier version) is converted
    # in place, keeping its history.
    old = tmp_path / "old"
    old.mkdir()
    (old / "n.md").write_text("n", encoding="utf-8")
    subprocess.run(["git", "-C", str(old), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(old), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(old),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-qm",
            "first",
        ],
        check=True,
    )
    assert is_repo(old)
    ensure_repo(old)
    assert (old / ".git").is_file() and (old / HISTORY_DIR).is_dir()
    assert [e.title for e in log(old)] == ["first"]
