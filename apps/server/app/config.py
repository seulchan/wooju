"""Brain path resolution and health/status derivation.

The Brain filesystem is the single source of truth. This module only *reads*
configuration and the filesystem — it never writes to the Brain (Invariant 4).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from .api.models import HealthResponse

ENV_VAR = "WOOJU_BRAIN_PATH"
# Set to a truthy value (1/true/yes/on) to disable live filesystem watching —
# e.g. on filesystems where inotify/FSEvents is unreliable, or to keep tests
# deterministic. When disabled, the index is built once at startup (restart to
# refresh). Read-only either way: the watcher only ever *reads* the Brain.
WATCH_DISABLE_VAR = "WOOJU_DISABLE_FILE_WATCH"


def watch_enabled() -> bool:
    """True unless ``WOOJU_DISABLE_FILE_WATCH`` is set to a truthy value."""
    return os.environ.get(WATCH_DISABLE_VAR, "").strip().lower() in ("", "0", "false", "no", "off")


# Load apps/server/.env so configuration (e.g. WOOJU_BRAIN_PATH) can live in a file
# instead of the shell. Real environment variables take precedence (override=False),
# so explicit exports or CI/production settings still win. .env is gitignored;
# copy .env.example to .env and edit it. Loading is CWD-independent: it always
# reads the .env sitting next to pyproject.toml (the server root).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env", override=False)


def resolve_brain_path() -> Path | None:
    """Resolve the configured Brain directory from the environment.

    Returns the absolute, user/variable-expanded path, or ``None`` when the
    environment variable is unset or blank. The path is returned even when it
    does not exist or is not a directory; those checks happen in
    :func:`build_health`.
    """
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    try:
        return Path(expanded).resolve()
    except (OSError, ValueError):
        # Fall back to an absolute path if symlink/escape resolution fails.
        return Path(expanded).absolute()


def build_health(brain_path: Path | None) -> HealthResponse:
    """Derive the health response from a resolved Brain path."""
    if brain_path is None:
        return HealthResponse(
            status="misconfigured",
            api="ok",
            brain_path=None,
            brain_configured=False,
            brain_exists=False,
            brain_is_directory=False,
            brain_valid=False,
            message=f"{ENV_VAR} is not set.",
        )

    exists = brain_path.exists()
    is_directory = brain_path.is_dir()
    brain_valid = exists and is_directory

    if brain_valid:
        status = "ok"
        message = "Brain directory is configured and accessible (empty is fine)."
    elif not exists:
        status = "misconfigured"
        message = f"Brain path does not exist: {brain_path}"
    else:
        status = "misconfigured"
        message = f"Brain path is not a directory: {brain_path}"

    return HealthResponse(
        status=status,
        api="ok",
        brain_path=str(brain_path),
        brain_configured=True,
        brain_exists=exists,
        brain_is_directory=is_directory,
        brain_valid=brain_valid,
        message=message,
    )
