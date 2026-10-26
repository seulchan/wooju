"""Connect Wooju to Claude Desktop with one click.

Claude Desktop starts MCP servers listed in its config file. Connecting adds a
``wooju`` entry that runs this app's own server binary with ``--mcp``; other
entries and settings in the file are kept as they are, and the previous file
is saved next to it as ``.bak``. A file Claude can't parse is never
overwritten. Claude must be restarted to pick up the change.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from brain_core.messages import UserFacingError

ENTRY = "wooju"


class ClaudeLinkError(UserFacingError):
    """``key`` names the user message."""


def config_path() -> Path:
    override = os.environ.get("WOOJU_CLAUDE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"


def claude_installed() -> bool:
    if os.environ.get("WOOJU_CLAUDE_CONFIG"):
        return True  # tests
    return any(
        (base / "Claude.app").is_dir()
        for base in (Path("/Applications"), Path.home() / "Applications")
    )


def server_command() -> dict[str, Any]:
    """How Claude should start Wooju's MCP server."""
    if getattr(sys, "frozen", False):
        # The bundled sidecar inside Wooju.app (Contents/MacOS/wooju-server).
        return {"command": sys.executable, "args": ["--mcp"]}
    return {"command": sys.executable, "args": ["-m", "app.launcher", "--mcp"]}


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaudeLinkError(str(exc), "claude.config_unreadable") from exc
    if not isinstance(data, dict):
        raise ClaudeLinkError("not an object", "claude.config_unreadable")
    return data


def status() -> dict[str, Any]:
    path = config_path()
    wanted = server_command()
    try:
        entry = (_read(path).get("mcpServers") or {}).get(ENTRY)
        readable = True
    except ClaudeLinkError:
        entry, readable = None, False
    connected = isinstance(entry, dict)
    current = connected and entry.get("command") == wanted["command"]
    return {
        "installed": claude_installed(),
        "connected": connected,
        # Connected, but to another copy of Wooju (e.g. the app was moved).
        "outdated": connected and not current,
        "config_readable": readable,
        "command": f"{wanted['command']} {' '.join(wanted['args'])}",
    }


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def connect() -> dict[str, Any]:
    if not claude_installed():
        raise ClaudeLinkError("Claude Desktop not found", "claude.not_installed")
    path = config_path()
    data = _read(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[ENTRY] = server_command()
    data["mcpServers"] = servers
    _write(path, data)
    return status()


def disconnect() -> dict[str, Any]:
    path = config_path()
    data = _read(path)
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and ENTRY in servers:
        del servers[ENTRY]
        _write(path, data)
    return status()
