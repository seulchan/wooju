"""UI-only state persisted outside the Brain.

``~/.wooju-brain-ui/state.json`` holds *presentation* state that must never be
written into the Brain (Invariant 4 in the plan). Today that is ``last_seen_at``
(when the user last looked at Home) and ``known`` — a disposable, rebuildable
snapshot of record ids present at that visit, used to distinguish newly-created
records from modified ones.

This module never reads or writes anything under the Brain; the Brain filesystem
stays canonical. All writes here are atomic (temp file + rename) and tolerate
missing/absent-only state. Invalid or corrupt state is never fatal — it degrades
to the first-run defaults (``last_seen_at=None``).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .api.models import UiState

logger = logging.getLogger("wooju")

# Matches the plan's example location: ~/.wooju-brain-ui/state.json
_DEFAULT_DIR = Path.home() / ".wooju-brain-ui"
_STATE_ENV_VAR = "WOOJU_UI_STATE_PATH"


def state_file() -> Path:
    """Absolute path to the UI-state file (override via ``WOOJU_UI_STATE_PATH``)."""
    override = os.environ.get(_STATE_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_DIR / "state.json"


def parse_isodate(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (lenient about ``Z``), or ``None`` if invalid/absent."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load() -> UiState:
    """Read the UI-state file, degrading to first-run defaults on any problem."""
    path = state_file()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return UiState()
    except OSError as exc:
        logger.warning("Could not read UI state %s: %s", path, exc)
        return UiState()

    try:
        data = json.loads(raw)
    except ValueError as exc:
        logger.warning("Ignoring corrupt UI state %s: %s", path, exc)
        return UiState()

    if not isinstance(data, dict):
        return UiState()

    # An absent *or* invalid last_seen_at means "first visit" semantics.
    last_seen = data.get("last_seen_at")
    if parse_isodate(last_seen) is None:
        last_seen = None

    known = data.get("known")
    if not isinstance(known, list):
        known = []
    known = [str(k) for k in known if isinstance(k, str) and k]

    return UiState(last_seen_at=last_seen, known=known)


def save(state: UiState) -> None:
    """Atomically write the UI-state file (never touches the Brain)."""
    path = state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create UI state dir %s: %s", path.parent, exc)
        return

    payload = json.dumps(
        {"last_seen_at": state.last_seen_at, "known": state.known},
        indent=2,
        default=str,
    )
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except OSError as exc:
        logger.warning("Could not write UI state %s: %s", path, exc)
