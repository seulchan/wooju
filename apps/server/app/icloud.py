"""Capture from the iPhone through iCloud Drive.

On the iPhone: Share → Save to Files → iCloud Drive → Wooju Inbox. When the
Mac is on and Wooju is open, files there are moved into the Brain's inbox and
organized like a dropped file. Nothing needs to be running on the phone, and
nothing is sent anywhere but iCloud, which the user already uses.

A file is taken only when it has stopped changing between two checks, so a
half-synced file is never read. iCloud placeholders (``.name.icloud``) are
skipped until they download. Short text files are what iOS makes from a shared
link or typed text, so they go through the link-or-memo rule; files Wooju
can't read are moved to a "Not supported" subfolder instead of being retried.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

FOLDER_NAME = "Wooju Inbox"
UNSUPPORTED = "Not supported"
# A text file at most this long is a shared link or a typed memo.
SHORT_TEXT = 1000


def icloud_drive() -> Path:
    override = os.environ.get("WOOJU_ICLOUD_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"


def capture_folder() -> Path:
    return icloud_drive() / FOLDER_NAME


def available() -> bool:
    return icloud_drive().is_dir()


def ensure_folder() -> Path:
    folder = capture_folder()
    folder.mkdir(exist_ok=True)
    return folder


@dataclass
class Watcher:
    """Remembers sizes between checks to tell finished files from syncing ones."""

    seen: dict[Path, tuple[int, float]] = field(default_factory=dict)

    def ready(self, folder: Path) -> list[Path]:
        if not folder.is_dir():
            return []
        out: list[Path] = []
        current: dict[Path, tuple[int, float]] = {}
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.name.startswith(".") or path.suffix == ".icloud":
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            sig = (stat.st_size, stat.st_mtime)
            current[path] = sig
            if self.seen.get(path) == sig and stat.st_size > 0:
                out.append(path)
        self.seen = {p: s for p, s in current.items() if p not in out}
        return out


def set_aside(path: Path) -> None:
    """Move a file Wooju can't read out of the way, keeping it for the user."""
    target_dir = path.parent / UNSUPPORTED
    target_dir.mkdir(exist_ok=True)
    target, n = target_dir / path.name, 2
    while target.exists():
        target, n = target_dir / f"{path.stem}-{n}{path.suffix}", n + 1
    shutil.move(str(path), target)


def short_text(path: Path) -> str | None:
    """The text of a short .txt (a shared link or memo), else None."""
    if path.suffix.lower() not in (".txt", ".text") or path.stat().st_size > SHORT_TEXT * 4:
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text if len(text) <= SHORT_TEXT else None
