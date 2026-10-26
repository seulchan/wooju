"""Capture from anywhere: links and memos, alongside dropped files.

* A **link** is fetched once and saved into ``inbox/`` as the page (HTML) or
  document (PDF). Its address is remembered in ``inbox/.links.json`` so the
  source note's ``canonical_ref`` is the real URL, not the local copy. Link
  files from Apple devices (``.webloc``, ``.url``) are treated the same way.
* A **memo** is the user's own words. It is not an outside source, and the
  Brain's rules keep passing thoughts out of durable memory, so it is kept in
  ``inbox/memos/`` as captured: searchable and askable, never rewritten.
"""

from __future__ import annotations

import ipaddress
import json
import plistlib
import re
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from brain_core.messages import UserFacingError

from .text import first_url

MEMO_DIR = "inbox/memos"
LINKS_FILE = "inbox/.links.json"
LINK_SUFFIXES = {".webloc", ".url"}
MAX_BYTES = 15 * 1024 * 1024
# A message that is a link plus a few words ("이거 읽어볼 것 https://...") is a link.
LINK_NOTE_CHARS = 200
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Wooju/0.1"


class CaptureError(UserFacingError):
    """``key`` names the user message."""


# ------------------------------------------------------------------ deciding


def classify_text(text: str) -> tuple[str, str]:
    """``("link", url)`` or ``("memo", text)`` for something the user typed or shared."""
    text = text.strip()
    if not text:
        raise CaptureError("empty", "capture.empty")
    url = first_url(text)
    if url and len(text.replace(url, "").strip()) <= LINK_NOTE_CHARS:
        return "link", url
    return "memo", text


# --------------------------------------------------------------------- memos


def _memo_title(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "Memo")
    first = re.sub(r"^#+\s*", "", first)
    return first if len(first) <= 60 else first[:59].rstrip() + "…"


def save_memo(brain: Path, text: str, *, via: str, now: datetime | None = None) -> str:
    """Write the memo as the user wrote it; return its Brain-relative path."""
    now = now or datetime.now().astimezone()
    folder = brain / MEMO_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stem = now.strftime("%Y-%m-%d-%H%M%S")
    target, n = folder / f"{stem}.md", 2
    while target.exists():
        target, n = folder / f"{stem}-{n}.md", n + 1
    frontmatter = {
        "title": _memo_title(text),
        "type": "memo",
        "captured_at": now.isoformat(timespec="seconds"),
        "via": via,
    }
    body = text.strip()
    target.write_text(
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return target.relative_to(brain).as_posix()


# --------------------------------------------------------------------- links


def _check_public(url: str) -> None:
    """Refuse anything but public http(s) addresses (no localhost, LAN, or files)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise CaptureError(url, "capture.bad_link")
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror as exc:
        raise CaptureError(str(exc), "capture.unreachable") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise CaptureError(url, "capture.bad_link")


def fetch(url: str, client: httpx.Client | None = None) -> tuple[bytes, str, str]:
    """Download a page or PDF: ``(data, suffix, final_url)``."""
    _check_public(url)
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    try:
        with client.stream("GET", url, headers={"User-Agent": _UA}) as resp:
            resp.raise_for_status()
            final = str(resp.url)
            _check_public(final)
            kind = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if kind == "application/pdf" or final.lower().endswith(".pdf"):
                suffix = ".pdf"
            elif kind in ("text/html", "application/xhtml+xml", ""):
                suffix = ".html"
            elif kind.startswith("text/"):
                suffix = ".txt"
            else:
                raise CaptureError(kind, "capture.unsupported_link")
            data = bytearray()
            for chunk in resp.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise CaptureError("too big", "capture.too_big")
    except httpx.HTTPStatusError as exc:
        raise CaptureError(str(exc), "capture.unreachable") from exc
    except httpx.HTTPError as exc:
        raise CaptureError(str(exc), "capture.unreachable") from exc
    return bytes(data), suffix, final


def _slug_for(url: str) -> str:
    parts = urlparse(url)
    tail = [p for p in parts.path.split("/") if p][-1:] or [""]
    raw = f"{parts.hostname or 'link'}-{tail[0]}"
    raw = re.sub(r"\.(html?|php|aspx?|pdf)$", "", raw, flags=re.I)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
    return slug[:60] or "link"


def remember_link(brain: Path, rel: str, url: str) -> None:
    path = brain / LINKS_FILE
    try:
        links = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        links = {}
    links = {k: v for k, v in links.items() if (brain / k).exists()}  # forget processed files
    links[rel] = url
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")


def link_for(brain: Path, rel: str) -> str | None:
    """The address an inbox file was fetched from, if it came from a link."""
    path = brain / LINKS_FILE
    try:
        links = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return None
    value = links.get(rel)
    return value if isinstance(value, str) else None


def save_link(brain: Path, url: str, client: httpx.Client | None = None) -> str:
    """Fetch ``url`` into ``inbox/``; return the saved file's Brain-relative path."""
    data, suffix, final = fetch(url, client)
    inbox = brain / "inbox"
    inbox.mkdir(exist_ok=True)
    stem = _slug_for(final)
    target, n = inbox / f"{stem}{suffix}", 2
    while target.exists():
        target, n = inbox / f"{stem}-{n}{suffix}", n + 1
    target.write_bytes(data)
    rel = target.relative_to(brain).as_posix()
    remember_link(brain, rel, final)
    return rel


def read_link_file(path: Path) -> str:
    """The URL inside a ``.webloc`` (macOS/iOS) or ``.url`` (Windows) link file."""
    raw = path.read_bytes()
    if path.suffix.lower() == ".webloc":
        try:
            value = plistlib.loads(raw).get("URL")
        except Exception as exc:  # noqa: BLE001 — any malformed plist
            raise CaptureError(str(exc), "capture.bad_link") from exc
    else:
        m = re.search(r"^URL=(.+)$", raw.decode("utf-8", "replace"), re.M)
        value = m.group(1).strip() if m else None
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise CaptureError(str(path), "capture.bad_link")
    return value
