"""Shared pieces of the engine: errors, jobs, folders, and Brain creation."""

from __future__ import annotations

import logging
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from brain_core import history
from brain_core.messages import UserFacingError

logger = logging.getLogger("wooju")

JobState = Literal["queued", "working", "waiting", "done", "failed"]
RETRY_SECONDS = 10.0
MAX_ATTEMPTS = 3


class SetupError(UserFacingError):
    """A setup or file problem; ``key`` names the user message."""

    def __init__(self, key: str, **params: Any) -> None:
        super().__init__(key, key, **params)


@dataclass
class Job:
    file: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: JobState = "queued"
    message: str | None = None
    proposal_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    attempts: int = 0  # tries that ended because the AI wasn't available
    conflicts: int = 0  # disagreements with existing notes, written into the note
    note_id: str | None = None  # the source note it became (for the user's one line)
    title: str | None = None  # what it was saved as (or the existing note, if a duplicate)
    # Existing notes that say nearly the same thing ({id, title}); a question, never a merge.
    similar: list[dict[str, str]] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)  # topics it was filed under
    # A long file is read in parts: {"done": n, "total": m} while it is being read.
    progress: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def template_dir() -> Path:
    override = os.environ.get("WOOJU_TEMPLATE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[4] / "template"


def samples_dir() -> Path:
    """Sample notes to look around with, one folder per language (``samples/<lang>``)."""
    override = os.environ.get("WOOJU_SAMPLES_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[4] / "samples"


SAMPLE_TAG = "sample"


def looks_like_brain(path: Path) -> bool:
    return (path / "wooju-brain.yaml").is_file() or (
        (path / "AGENTS.md").is_file() and (path / "wiki").is_dir()
    )


def create_or_open_brain(path: Path) -> bool:
    """Open an existing Brain or create one from the template. Returns True if created."""
    path = path.expanduser()
    if path.exists() and not path.is_dir():
        raise SetupError("setup.not_folder")
    if path.is_dir() and looks_like_brain(path):
        return False
    if path.is_dir() and any(p for p in path.iterdir() if not p.name.startswith(".")):
        raise SetupError("setup.folder_busy")
    template = template_dir()
    if not template.is_dir():
        raise SetupError("setup.broken_install")
    shutil.copytree(template, path, dirs_exist_ok=True, symlinks=True)
    history.ensure_repo(path)
    return True


def _safe_upload_name(name: str) -> str:
    base = Path(name).name.strip().lstrip(".")
    base = re.sub(r"[\x00-\x1f/\\:]", "_", base)
    return base or "file"
