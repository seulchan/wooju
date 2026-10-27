"""Taking things in: dropped files, memos, links, and the iCloud folder."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brain_core import history
from brain_core.messages import UserFacingError, render
from wooju_agents.capture import (
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


class CaptureMixin:
    """Part of :class:`app.engine.Engine`; uses its state (``self.brain``, ``self.index``...)."""

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

    async def receive(self, name: str, data: bytes) -> str:
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
        return rel

    def saved_source_for(self, *urls: str | None) -> Any:
        """The source note already saved from one of these addresses, if any."""
        wanted = {u.rstrip("/") for u in urls if u}
        for record in self.index.sources():
            ref = record.metadata.get("canonical_ref")
            if isinstance(ref, str) and ref.rstrip("/") in wanted:
                return record
        return None

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
            if existing is not None:
                return {"kind": "link", "url": value, "duplicate": True, "title": existing.title}
            pending = self.pending_link_file(value)
            if pending is not None:  # fetched before and not organized yet: try again
                job = await self.enqueue(pending)
                return {"kind": "link", "file": pending, "url": value, "job": job.to_dict()}
            rel = await asyncio.to_thread(save_link, brain, value)
            async with self.lock:
                await asyncio.to_thread(
                    history.commit_paths, brain, [rel, "inbox/.links.json"], f"Received {value}"
                )
            job = await self.enqueue(rel)
            return {"kind": "link", "file": rel, "url": value, "job": job.to_dict()}
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
                    rel = await self.receive(path.name, data)
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
