"""Structural validator for a Brain (OPERATIONS.md "Validation").

The validator checks structure, not truth: frontmatter against the layer
schemas, links, required sections, naming, sensitive data, placeholders,
duplicates, and orphans. It never writes to the Brain.

Severity:

* ``error`` — breaks a rule the Brain constitution states as required. A Brain
  with errors must not accept the change that introduced them.
* ``warning`` — a recommended convention is missing or something looks off.
  Warnings never block a change.

Command line::

    wooju-validate /path/to/brain [--json]

Exit status is 1 when any error is found, otherwise 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from .markdown import extract_title, normalize_text
from .reader import read_records
from .relationships import resolve_relationships
from .schema import CONTENT_ROOTS, SCHEMAS, WIKI_SECTIONS, layer_for

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    path: str
    message: str
    line: int | None = None


@dataclass
class Report:
    root: str
    files_checked: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "files_checked": self.files_checked,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "issues": [asdict(i) for i in self.issues],
        }


# ----------------------------------------------------------------- patterns

_KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
_NAME_EXEMPT = {"README.md", "index.md"}
_FENCE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_MD_LINK = re.compile(r"(?<!\!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|lorem ipsum|\{\{[^}]*\}\}", re.IGNORECASE)

_SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
)
_URL = re.compile(r"(?:https?://|www\.)\S+")
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_RRN = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
_PASSWORD = re.compile(r"(?im)^\s*[-*]?\s*(password|passwd|비밀번호)\s*[:=]\s*\S+")


def _luhn(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# ------------------------------------------------------------------ parsing


@dataclass
class _Note:
    rel: PurePosixPath
    text: str
    frontmatter: dict[str, Any]
    body: str
    body_offset: int  # line number (1-based) where the body starts
    layer: str | None


def _parse_strict(rel: str, text: str, issues: list[Issue]) -> tuple[dict[str, Any], str, int]:
    """Split frontmatter, reporting problems instead of hiding them."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text, 1
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        issues.append(
            Issue("error", "frontmatter", rel, "Frontmatter starts with '---' but never closes.", 1)
        )
        return {}, text, 1
    raw = "\n".join(lines[1:close])
    body = "\n".join(lines[close + 1 :])
    if not raw.strip():
        return {}, body, close + 2
    try:
        data = yaml.safe_load(raw)
    except ValueError as exc:  # PyYAML raises ValueError for impossible dates
        issues.append(
            Issue("error", "frontmatter", rel, f"Frontmatter has an impossible value: {exc}", 1)
        )
        return {}, body, close + 2
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 2 if mark is not None else 1
        issues.append(
            Issue("error", "frontmatter", rel, f"Frontmatter is not valid YAML: {exc}", line)
        )
        return {}, body, close + 2
    if not isinstance(data, dict):
        issues.append(
            Issue("error", "frontmatter", rel, "Frontmatter must be a key: value mapping.", 1)
        )
        return {}, body, close + 2
    return data, body, close + 2


def _iter_markdown(root: Path):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith(".") or not name.endswith(".md"):
                continue
            path = Path(dirpath) / name
            if not path.is_symlink():
                yield path


def _quality_mode(root: Path) -> str:
    config = root / "wooju-brain.yaml"
    try:
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        mode = (data.get("knowledge") or {}).get("quality_mode")
        return mode if mode in ("standard", "rigorous") else "standard"
    except (OSError, yaml.YAMLError, AttributeError):
        return "standard"


# --------------------------------------------------------------- body helpers


def _sections(body: str) -> list[tuple[int, str, bool, int]]:
    """Return ``(level, title, has_content, line_index)`` for each heading."""
    stripped = _FENCE.sub(lambda m: "x\n" * m.group(0).count("\n") + "x", body)
    lines = stripped.split("\n")
    heads = [(i, _HEADING.match(line)) for i, line in enumerate(lines)]
    heads = [(i, m) for i, m in heads if m]
    out = []
    for n, (i, m) in enumerate(heads):
        level = len(m.group(1))
        end = len(lines)
        for j, m2 in heads[n + 1 :]:
            if len(m2.group(1)) <= level:
                end = j
                break
        # Content = any non-blank line that is not itself a deeper heading.
        has = any(
            lines[k].strip() and not _HEADING.match(lines[k]) for k in range(i + 1, end)
        ) or any(i < j < end for j, _ in heads)
        out.append((level, m.group(2).strip(), has, i))
    return out


def _has_section(body: str, title: str) -> bool:
    wanted = title.strip().lower()
    return any(t.lower() == wanted for _lvl, t, _has, _i in _sections(body))


# ------------------------------------------------------------------ checks


def _check_schema(note: _Note, issues: list[Issue]) -> None:
    rel = note.rel.as_posix()
    schema = SCHEMAS.get(note.layer or "")
    if schema is None:
        return
    try:
        schema.model_validate(note.frontmatter)
    except ValidationError as exc:
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "frontmatter"
            msg = err["msg"]
            if err["type"] == "missing":
                msg = "required field is missing"
            issues.append(Issue("error", "schema", rel, f"{where}: {msg}", 1))


def _check_recommended(note: _Note, issues: list[Issue]) -> None:
    rel, fm, layer = note.rel.as_posix(), note.frontmatter, note.layer

    def warn(code: str, msg: str) -> None:
        issues.append(Issue("warning", code, rel, msg, 1))

    if layer == "source":
        for key in ("title", "published", "accessed"):
            if fm.get(key) in (None, ""):
                warn("recommended", f"{key}: recommended for source notes")
    elif layer == "memory_record":
        if fm.get("observed_at") in (None, ""):
            warn("recommended", "observed_at: recommended so the record's age is known")
        if fm.get("provenance") == "inferred":
            warn(
                "inferred-memory",
                "Inferred memory: keep the supporting evidence in the body and "
                "confirm with the user before relying on it.",
            )
    elif layer == "memory_state":
        if fm.get("provenance") in (None, ""):
            warn("recommended", "provenance: recommended for state pages")

    status = fm.get("status")
    if status == "superseded" and not fm.get("superseded_by") and layer != "source":
        warn(
            "supersession",
            "Marked superseded without superseded_by; link the replacement when one exists.",
        )
    if layer and layer.startswith("memory") and status == "current" and fm.get("superseded_by"):
        issues.append(
            Issue(
                "error",
                "supersession",
                rel,
                "Marked current but names a replacement in superseded_by.",
                1,
            )
        )


def _check_insight(note: _Note, issues: list[Issue]) -> None:
    if note.layer != "insight":
        return
    rel = note.rel.as_posix()
    status = note.frontmatter.get("status")
    if not _has_section(note.body, "Challenge"):
        if status in ("provisional", "established"):
            issues.append(
                Issue(
                    "error",
                    "challenge",
                    rel,
                    f"A {status} insight needs a '## Challenge' section.",
                    None,
                )
            )
        else:
            issues.append(
                Issue(
                    "warning",
                    "challenge",
                    rel,
                    "Add a '## Challenge' section before promoting past candidate.",
                    None,
                )
            )
    if not _has_section(note.body, "Insight"):
        issues.append(
            Issue(
                "warning",
                "insight-shape",
                rel,
                "Recommended: an '## Insight' section stating the derived relationship.",
                None,
            )
        )


def _check_location_and_name(note: _Note, issues: list[Issue]) -> None:
    rel = note.rel.as_posix()
    parts = note.rel.parts
    if parts[0] == "wiki":
        if len(parts) == 2 and parts[1] not in _NAME_EXEMPT:
            issues.append(
                Issue(
                    "error",
                    "location",
                    rel,
                    f"Wiki pages belong in one of: {', '.join(WIKI_SECTIONS)}.",
                    None,
                )
            )
        elif len(parts) > 2 and parts[1] not in WIKI_SECTIONS:
            issues.append(
                Issue(
                    "error",
                    "location",
                    rel,
                    f"Unknown wiki section '{parts[1]}'. Use one of: {', '.join(WIKI_SECTIONS)}.",
                    None,
                )
            )
    if note.rel.name not in _NAME_EXEMPT and not _KEBAB.match(note.rel.name):
        issues.append(
            Issue(
                "warning",
                "naming",
                rel,
                "Prefer lowercase kebab-case file names (e.g. 'gross-margin.md').",
                None,
            )
        )


def _check_body_text(note: _Note, issues: list[Issue], durable: bool) -> None:
    rel, text = note.rel.as_posix(), note.text
    for label, pattern in _SECRETS:
        for m in pattern.finditer(text):
            issues.append(
                Issue(
                    "error",
                    "sensitive",
                    rel,
                    f"Looks like a {label}. Secrets never belong in the Brain.",
                    _line_of(text, m.start()),
                )
            )
    # Number-shaped secrets are checked outside URLs: article IDs in links
    # (e.g. news/202608270824322215) can pass a Luhn check by chance.
    no_urls = _URL.sub(lambda m: " " * len(m.group(0)), text)
    for m in _CARD.finditer(no_urls):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits) and len(set(digits)) > 1:
            issues.append(
                Issue(
                    "error",
                    "sensitive",
                    rel,
                    "Looks like a payment card number. Secrets never belong in the Brain.",
                    _line_of(text, m.start()),
                )
            )
    for m in _RRN.finditer(no_urls):
        issues.append(
            Issue(
                "error",
                "sensitive",
                rel,
                "Looks like a Korean resident registration number. "
                "Secrets never belong in the Brain.",
                _line_of(text, m.start()),
            )
        )
    for m in _PASSWORD.finditer(text):
        issues.append(
            Issue(
                "warning",
                "sensitive",
                rel,
                "Looks like a password. Remove it unless it is an example.",
                _line_of(text, m.start()),
            )
        )
    if not durable:
        return
    body_clean = _FENCE.sub("", note.body)
    for m in _PLACEHOLDER.finditer(body_clean):
        issues.append(
            Issue("warning", "placeholder", rel, f"Placeholder text '{m.group(0)}'.", None)
        )
    for level, title, has, i in _sections(note.body):
        if level >= 2 and not has:
            issues.append(
                Issue(
                    "warning",
                    "empty-section",
                    rel,
                    f"Section '{title}' is empty.",
                    note.body_offset + i,
                )
            )


def _check_md_links(
    note: _Note, root: Path, issues: list[Issue], inbound: dict[str, set[str]]
) -> None:
    rel = note.rel.as_posix()
    body = _FENCE.sub("", note.body)
    for m in _MD_LINK.finditer(body):
        target = m.group(1).split("#", 1)[0]
        if not target or _SCHEME.match(target):
            continue
        base = root if target.startswith("/") else (root / note.rel.parent)
        resolved = (base / target.lstrip("/")).resolve()
        try:
            tgt_rel = resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            issues.append(
                Issue(
                    "error",
                    "broken-link",
                    rel,
                    f"Link points outside the Brain: {m.group(1)}",
                    None,
                )
            )
            continue
        if not resolved.exists():
            issues.append(
                Issue(
                    "error", "broken-link", rel, f"Link target does not exist: {m.group(1)}", None
                )
            )
            continue
        if tgt_rel.startswith("inbox/"):
            issues.append(
                Issue(
                    "error",
                    "inbox-link",
                    rel,
                    "Durable pages must not link to temporary inbox files.",
                    None,
                )
            )
        if tgt_rel.endswith(".md"):
            inbound[tgt_rel[:-3]].add(rel)


# --------------------------------------------------------------- entry point


def validate_brain(root: Path) -> Report:
    """Validate the Brain at ``root`` and return every issue found."""
    root = Path(root)
    report = Report(root=str(root))
    if not root.is_dir():
        report.issues.append(Issue("error", "root", str(root), "Brain folder does not exist."))
        return report

    issues = report.issues
    notes: list[_Note] = []
    for path in _iter_markdown(root):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        try:
            text = normalize_text(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(Issue("error", "unreadable", rel.as_posix(), f"Cannot read file: {exc}"))
            continue
        top = rel.parts[0] if len(rel.parts) > 1 else ""
        if top not in CONTENT_ROOTS and top not in ("inbox", "logs"):
            continue  # root files, docs/, archive/, indexes/, scripts/
        report.files_checked += 1
        local: list[Issue] = []
        fm, body, offset = _parse_strict(rel.as_posix(), text, local)
        issues.extend(local)
        layer = layer_for(rel.parts, fm) if top in CONTENT_ROOTS else None
        notes.append(_Note(rel, text, fm, body, offset, layer))

    # Relationship resolution reuses the same logic the UI uses.
    records = read_records(root)
    resolve_relationships(records)
    inbound: dict[str, set[str]] = defaultdict(set)
    for rec in records.values():
        for link in rec.links:
            if link.resolved_id:
                inbound[link.resolved_id].add(rec.path)
        for ref in rec.derived_from_resolved:
            if ref.resolved_id:
                inbound[ref.resolved_id].add(rec.path)

    titles: dict[tuple[str, str], list[str]] = defaultdict(list)
    for note in notes:
        rel = note.rel.as_posix()
        durable = note.layer is not None
        _check_body_text(note, issues, durable)
        if not durable:
            continue
        _check_schema(note, issues)
        _check_recommended(note, issues)
        _check_insight(note, issues)
        _check_location_and_name(note, issues)
        _check_md_links(note, root, issues, inbound)

        rec = records.get(rel[:-3])
        if rec is not None:
            for link in rec.links:
                if link.kind == "markdown":
                    continue  # checked against the files themselves by _check_md_links
                if link.resolved_id is None:
                    issues.append(
                        Issue(
                            "error",
                            "broken-link",
                            rel,
                            f"Wikilink [[{link.target}]] does not match any note.",
                            None,
                        )
                    )
                elif link.resolved_id.startswith("inbox/"):
                    issues.append(
                        Issue(
                            "error",
                            "inbox-link",
                            rel,
                            "Durable pages must not link to temporary inbox files.",
                            None,
                        )
                    )
            for ref in rec.derived_from_resolved:
                if ref.resolved_id is None:
                    issues.append(
                        Issue(
                            "error",
                            "broken-link",
                            rel,
                            f"derived_from entry '{ref.ref}' does not match any note.",
                            1,
                        )
                    )
        title = extract_title(note.frontmatter, note.body, note.rel.stem).strip().lower()
        layer_key = "memory" if (note.layer or "").startswith("memory") else (note.layer or "")
        titles[(layer_key, title)].append(rel)

    for (_layer, _title), paths in titles.items():
        if len(paths) > 1:
            for p in paths:
                others = ", ".join(x for x in paths if x != p)
                issues.append(
                    Issue(
                        "warning",
                        "duplicate-title",
                        p,
                        f"Same title as {others}. Merge or rename if they cover the same thing.",
                    )
                )

    rigorous = _quality_mode(root) == "rigorous"
    for note in notes:
        if note.layer not in ("wiki", "insight") or note.rel.parts[0] != "wiki":
            continue
        rel_id = note.rel.as_posix()[:-3]
        if note.rel.name not in _NAME_EXEMPT and not inbound.get(rel_id):
            issues.append(
                Issue(
                    "warning",
                    "orphan",
                    note.rel.as_posix(),
                    "No other note links here. Link it from a related page, overview, or area.",
                )
            )
        if rigorous and not note.frontmatter.get("epistemic"):
            issues.append(
                Issue(
                    "warning",
                    "epistemic",
                    note.rel.as_posix(),
                    "Rigorous mode: add an epistemic block for material claims.",
                )
            )

    issues.sort(key=lambda i: (i.path, 0 if i.severity == "error" else 1, i.line or 0, i.code))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wooju-validate", description="Validate a Wooju Brain folder."
    )
    parser.add_argument("brain", type=Path, help="Path to the Brain folder")
    parser.add_argument("--json", action="store_true", help="Print a JSON report")
    args = parser.parse_args(argv)

    report = validate_brain(args.brain)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        current = None
        for issue in report.issues:
            if issue.path != current:
                current = issue.path
                print(f"\n{current}")
            where = f":{issue.line}" if issue.line else ""
            print(f"  {issue.severity:7} {issue.code:16}{where} {issue.message}")
        print(
            f"\n{report.files_checked} files checked: "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings"
        )
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
