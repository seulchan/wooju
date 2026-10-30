"""Taking things in: dropped files, memos, links, and the iCloud folder."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brain_core import history
from brain_core.changes import data_dir
from brain_core.messages import UserFacingError, render
from wooju_agents.capture import (
    CaptureError,
    classify_text,
    link_for,
    save_link,
    save_memo,
)
from wooju_agents.text import ACCEPTED_SUFFIXES

from .. import icloud
from .. import settings as app_settings
from .base import (
    SetupError,
    _safe_upload_name,
)


def _received_file():
    return data_dir() / "received.json"


class CaptureMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

    # How each inbox file arrived ("app", "icloud", "telegram"), kept in the
    # app's data folder until the file is organized; the note then records it
    # in its own made_by, so the Brain keeps it without the app.

    def remember_via(self, rel: str, via: str) -> None:
        path = _received_file()
        try:
            known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            known = {}
        known[rel] = via
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def via_for(self, rel: str) -> str:
        """How an inbox file arrived; "app" when unknown (dropped in the folder)."""
        try:
            known = json.loads(_received_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "app"
        value = known.get(rel) if isinstance(known, dict) else None
        return value if value in ("app", "icloud", "telegram", "claude") else "app"

    def forget_via(self, rel: str) -> None:
        path = _received_file()
        try:
            known = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(known, dict) and known.pop(rel, None) is not None:
                path.write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError):
            pass

    def save_upload(self, name: str, data: bytes) -> str:
        brain = self._require_brain()
        inbox = brain / "inbox"
        inbox.mkdir(exist_ok=True)
        base = _safe_upload_name(name)
        stem, suffix = Path(base).stem, Path(base).suffix
        if suffix.lower() not in ACCEPTED_SUFFIXES:
            raise SetupError("upload.unsupported", name=base)
        target, n = inbox / base, 2
        while target.exists():
            target, n = inbox / f"{stem}-{n}{suffix}", n + 1
        target.write_bytes(data)
        return target.relative_to(brain).as_posix()

    async def receive(self, name: str, data: bytes, *, via: str = "app") -> str:
        """Save an upload into ``inbox/`` and record it in history first.

        Recording the original before ingest means undoing the saved source
        brings the original file back instead of losing it.
        """
        brain = self._require_brain()
        async with self.lock:
            rel = self.save_upload(name, data)
            await asyncio.to_thread(
                history.commit_paths, brain, [rel], f"Received {Path(rel).name}"
            )
        self.remember_via(rel, via)
        return rel

    def saved_source_for(self, *urls: str | None) -> Any:
        """The source note already saved from one of these addresses, if any."""
        wanted = {u.rstrip("/") for u in urls if u}
        found = None
        for record in self.index.sources():
            ref = record.metadata.get("canonical_ref")
            if isinstance(ref, str) and ref.rstrip("/") in wanted:
                if not record.retired:
                    return record  # the current version
                found = found or record
        return found

    def pending_link_file(self, url: str) -> str | None:
        """An inbox file already fetched from ``url`` and not organized yet."""
        brain = self._require_brain()
        inbox = brain / "inbox"
        for path in inbox.glob("*") if inbox.is_dir() else []:
            rel = path.relative_to(brain).as_posix()
            if path.is_file() and link_for(brain, rel) in (url, url.rstrip("/")):
                return rel
        return None

    async def receive_text(self, text: str, *, via: str) -> dict[str, Any]:
        """A link or memo from the app, iCloud, or Telegram.

        A link is fetched into the inbox and queued like a dropped file; a memo
        is saved as written. Raises CaptureError (shown to the user).
        """
        brain = self._require_brain()
        kind, value = classify_text(text)
        if kind == "link":
            existing = self.saved_source_for(value)
            pending = self.pending_link_file(value)
            if pending is not None:  # fetched before and not organized yet: try again
                job = await self.enqueue(pending)
                return {"kind": "link", "file": pending, "url": value, "job": job.to_dict()}
            try:
                rel = await asyncio.to_thread(save_link, brain, value)
            except CaptureError:
                if existing is None:
                    raise
                # Saved before and can't be fetched now: nothing new to compare.
                return {"kind": "link", "url": value, "duplicate": True, "title": existing.title}
            async with self.lock:
                await asyncio.to_thread(
                    history.commit_paths, brain, [rel, "inbox/.links.json"], f"Received {value}"
                )
            self.remember_via(rel, via)
            job = await self.enqueue(rel)
            out = {"kind": "link", "file": rel, "url": value, "job": job.to_dict()}
            if existing is not None:  # saved before: the job checks whether it changed
                out |= {"recheck": True, "title": existing.title}
            return out
        async with self.lock:
            rel = await asyncio.to_thread(save_memo, brain, value, via=via)
            await asyncio.to_thread(history.commit_paths, brain, [rel], f"Memo: {Path(rel).stem}")
            await asyncio.to_thread(self.index.scan, brain)
        return {"kind": "memo", "file": rel}

    def _log_capture(self, via: str, kind: str, name: str, message: str | None = None) -> None:
        entry = {
            "via": via,
            "kind": kind,
            "name": name,
            "message": message,
            "at": datetime.now(UTC).isoformat(),
        }
        self.capture_log = [entry, *self.capture_log][:20]

    async def poll_icloud(self) -> int:
        """Take finished files from iCloud Drive/Wooju Inbox. Returns how many."""
        if self.brain is None or not app_settings.load().capture.icloud:
            return 0
        folder = icloud.capture_folder()
        files = await asyncio.to_thread(self.icloud_watch.ready, folder)
        taken = 0
        for path in files:
            try:
                text = await asyncio.to_thread(icloud.short_text, path)
                if text is not None:
                    result = await self.receive_text(text, via="icloud")
                    self._log_capture("icloud", result["kind"], path.name)
                elif path.suffix.lower() in ACCEPTED_SUFFIXES:
                    data = await asyncio.to_thread(path.read_bytes)
                    rel = await self.receive(path.name, data, via="icloud")
                    await self.enqueue(rel)
                    self._log_capture("icloud", "file", path.name)
                else:
                    await asyncio.to_thread(icloud.set_aside, path)
                    self._log_capture(
                        "icloud",
                        "refused",
                        path.name,
                        render("upload.unsupported", self.language(), name=path.name),
                    )
                    continue
            except UserFacingError as exc:
                await asyncio.to_thread(icloud.set_aside, path)
                self._log_capture("icloud", "refused", path.name, exc.localized(self.language()))
                continue
            path.unlink(missing_ok=True)
            taken += 1
        return taken
