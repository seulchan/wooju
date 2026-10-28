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
# Link files are accepted as input and turned into the fetched page first.
LINK_FILE_SUFFIXES = {".webloc", ".url"}
ACCEPTED_SUFFIXES = SUPPORTED_SUFFIXES | LINK_FILE_SUFFIXES

# Local models write "2026 년 7 월"; Korean attaches number units directly.
_DIGIT_UNIT = re.compile(
    r"(\d)\s+(년|월|일|차|개|명|분|초|시간|시|조|억|만|원|배|위|회|건|주|대|곳|%)"
)
_URL = re.compile(r"https?://[^\s)\]>\"']+")


class UnsupportedFile(Exception):
    pass


def normalize_korean(text: str) -> str:
    return _DIGIT_UNIT.sub(r"\1\2", text)


_SPACED = re.compile(r"[가-힣] (?=[가-힣])")
_ATTACHED = re.compile(r"[가-힣](?=[가-힣])")


def unspace_hangul(line: str) -> str:
    """Undo PDF text that puts a space between every Korean syllable.

    Some PDFs extract as "주 요  투 자 은 행": one space inside a word, two
    between words. Such a line has more spaced syllables than attached ones;
    it gets its single spaces removed and double spaces made single. Normal
    lines are left alone.
    """
    spaced = len(_SPACED.findall(line))
    if spaced < 3 or spaced <= len(_ATTACHED.findall(line)):
        return line
    indent = line[: len(line) - len(line.lstrip())]
    words = re.split(r" {2,}", line.strip())
    joined = " ".join(w.replace(" ", "") for w in words)
    # The space after punctuation or a bullet was lost with the others.
    joined = re.sub(r"([,.:;)])(?=[^\s\d,.:;)])", r"\1 ", joined)
    joined = re.sub(r"^([○■□▢※•·◦●▪-])(?=\S)", r"\1 ", joined)
    return indent + joined


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
        pages: list[str] = []
        size = 0
        for page in reader.pages[:300]:
            if size > max_chars:
                break  # enough text; long books are not read past the cap anyway
            pages.append(page.extract_text() or "")
            size += len(pages[-1])
        text = "\n".join(unspace_hangul(line) for line in "\n".join(pages).splitlines())
        meta_title = (reader.metadata or {}).get("/Title") if reader.metadata else None
        title = str(meta_title) if meta_title else None
    else:
        raise UnsupportedFile(path.suffix)
    text = text.replace("\x00", " ")  # some PDFs put NUL where a space belongs
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars], title


_HANGUL = re.compile(r"[\uac00-\ud7a3]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str | None:
    """The language a piece of text is written in (``ko``/``en``), or None if unclear.

    Counts Hangul syllables against Latin letters; Korean text full of English
    terms still reads as Korean because a syllable carries more than a letter.
    """
    sample = text[:20000]
    hangul = len(_HANGUL.findall(sample))
    latin = len(_LATIN.findall(sample))
    if hangul >= 20 and hangul >= 0.3 * (hangul + latin):
        return "ko"
    if latin >= 60:
        return "en"
    return None


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
