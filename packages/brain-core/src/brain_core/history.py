"""Brain history: every accepted change is a git commit, every commit can be undone.

Uses dulwich (pure-Python git), so the user never needs git installed. Only the
paths a change touches are staged, so unrelated edits the user made in another
editor are never swept into an app commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dulwich import porcelain
from dulwich.diff_tree import tree_changes
from dulwich.objects import Commit
from dulwich.repo import Repo

AUTHOR = b"Wooju <wooju@localhost>"


class HistoryError(Exception):
    """A history operation cannot be completed safely."""


@dataclass(frozen=True)
class Entry:
    id: str
    message: str
    title: str
    committed_at: str
    paths: tuple[str, ...]
    undoes: str | None = None


def is_repo(brain: Path) -> bool:
    return (brain / ".git").is_dir()


def ensure_repo(brain: Path) -> None:
    """Make ``brain`` a git repository with an initial commit if it is not one."""
    if is_repo(brain):
        return
    porcelain.init(str(brain))
    files = [
        p for p in brain.rglob("*") if p.is_file() and ".git" not in p.relative_to(brain).parts
    ]
    if files:
        porcelain.add(str(brain), paths=[str(p) for p in files])
    porcelain.commit(str(brain), message=b"Start this Brain", author=AUTHOR, committer=AUTHOR)


def commit_paths(brain: Path, paths: list[str], message: str) -> str:
    """Stage exactly ``paths`` (added, changed, or deleted) and commit them."""
    ensure_repo(brain)
    repo = Repo(str(brain))
    try:
        present = [str(brain / p) for p in paths if (brain / p).exists()]
        removed = [p for p in paths if not (brain / p).exists()]
        if present:
            porcelain.add(repo, paths=present)
        if removed:
            index = repo.open_index()
            for rel in removed:
                key = rel.encode("utf-8")
                if key in index:
                    del index[key]
            index.write()
        head = repo.head()
        if repo.open_index().commit(repo.object_store) == repo[head].tree:
            return head.decode("ascii")  # nothing changed; no empty commits
        sha = porcelain.commit(
            repo, message=message.encode("utf-8"), author=AUTHOR, committer=AUTHOR
        )
        return sha.decode("ascii")
    finally:
        repo.close()


def _changed_paths(repo: Repo, commit: Commit) -> list[tuple[str, bytes | None, bytes | None]]:
    """``(path, old_blob_sha, new_blob_sha)`` for each path a commit changed."""
    parent_tree = repo[commit.parents[0]].tree if commit.parents else None
    out = []
    for change in tree_changes(repo.object_store, parent_tree, commit.tree):
        old, new = change.old, change.new
        path = (new.path if new and new.path else old.path).decode("utf-8")
        out.append(
            (path, old.sha if old and old.sha else None, new.sha if new and new.sha else None)
        )
    return out


def log(brain: Path, limit: int = 50) -> list[Entry]:
    """Most recent commits first."""
    if not is_repo(brain):
        return []
    repo = Repo(str(brain))
    try:
        entries = []
        for walk in repo.get_walker(max_entries=limit):
            c = walk.commit
            message = c.message.decode("utf-8", "replace")
            undoes = None
            for line in message.splitlines():
                if line.startswith("Undoes: "):
                    undoes = line.removeprefix("Undoes: ").strip()
            entries.append(
                Entry(
                    id=c.id.decode("ascii"),
                    message=message,
                    title=message.splitlines()[0] if message else "",
                    committed_at=datetime.fromtimestamp(c.commit_time, tz=UTC).isoformat(),
                    paths=tuple(p for p, _o, _n in _changed_paths(repo, c)),
                    undoes=undoes,
                )
            )
        return entries
    finally:
        repo.close()


def undo(brain: Path, commit_id: str) -> str:
    """Create a new commit that reverses ``commit_id``.

    Refuses when a path was changed again after that commit, so a later edit
    (by the user or the app) is never silently thrown away.
    """
    repo = Repo(str(brain))
    try:
        try:
            commit = repo[commit_id.encode("ascii")]
        except KeyError as exc:
            raise HistoryError("That change is not in this Brain's history.") from exc
        if not isinstance(commit, Commit) or not commit.parents:
            raise HistoryError("The first commit of a Brain cannot be undone.")
        changes = _changed_paths(repo, commit)
        for path, _old, new in changes:
            target = brain / path
            current = target.read_bytes() if target.exists() else None
            expected = repo[new].data if new else None
            if current != expected:
                raise HistoryError(
                    f"'{path}' changed again after this change, so it was not undone."
                )
        for path, old, _new in changes:
            target = brain / path
            if old is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(repo[old].data)
        title = commit.message.decode("utf-8", "replace").splitlines()[0]
    finally:
        repo.close()
    return commit_paths(
        brain, [p for p, _o, _n in changes], f"Undo: {title}\n\nUndoes: {commit_id}"
    )
