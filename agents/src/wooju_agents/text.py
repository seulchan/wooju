"""Deterministic text helpers: extraction from dropped files and Korean clean-up."""

from __future__ import annotations

import html
import locale
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

SUPPORTED_LANGUAGES = ("ko", "en")
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}
HTML_SUFFIXES = {".html", ".htm"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | HTML_SUFFIXES | PDF_SUFFIXES

# Local models write "2026 년 7 월"; Korean attaches number units directly.
_DIGIT_UNIT = re.compile(
    r"(\d)\s+(년|월|일|차|개|명|분|초|시간|시|조|억|만|원|배|위|회|건|주|대|곳|%)"
)
_URL = re.compile(r"https?://[^\s)\]>\"']+")


class UnsupportedFile(Exception):
    pass


def normalize_korean(text: str) -> str:
    return _DIGIT_UNIT.sub(r"\1\2", text)


def first_url(text: str) -> str | None:
    m = _URL.search(text)
    return m.group(0).rstrip(".,") if m else None


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title: str | None = None
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and self.title is None and data.strip():
            self.title = data.strip()
        if not self._skip:
            self.parts.append(data)


def extract_text(path: Path, max_chars: int = 20000) -> tuple[str, str | None]:
    """Return ``(text, title_hint)`` from a supported file."""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text, title = path.read_text(encoding="utf-8", errors="replace"), None
    elif suffix in HTML_SUFFIXES:
        parser = _TextOnly()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        text, title = html.unescape("".join(parser.parts)), parser.title
    elif suffix in PDF_SUFFIXES:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
        meta_title = (reader.metadata or {}).get("/Title") if reader.metadata else None
        title = str(meta_title) if meta_title else None
    else:
        raise UnsupportedFile(path.suffix)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars], title


def resolve_language(setting: str | None) -> str:
    """Turn ``content.language`` (``auto`` or a tag) into a supported language."""
    value = (setting or "auto").strip().lower()
    if value != "auto":
        return value.split("-")[0] if value.split("-")[0] in SUPPORTED_LANGUAGES else "en"
    override = os.environ.get("WOOJU_LANGUAGE", "").strip().lower()
    candidates = [override] if override else []
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout
            candidates += re.findall(r'"?([a-zA-Z]{2})(?:-[A-Za-z]+)*"?', out)
        except (OSError, subprocess.SubprocessError):
            pass
    lang = locale.getlocale()[0] or os.environ.get("LANG", "")
    candidates.append(lang)
    for c in candidates:
        code = (c or "")[:2].lower()
        if code in SUPPORTED_LANGUAGES:
            return code
    return "en"
