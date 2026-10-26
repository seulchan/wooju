"""Measure local model quality on a real Brain (phase 1 gate).

Runs three tasks that the Ingest agent will need, against every note in a Brain,
for each Ollama model, and writes a JSON result plus a Markdown report:

1. classify  — pick the note's destination folder from its body alone.
2. source_fm — produce source-note frontmatter as JSON constrained by the
               brain-core schema, then validate it and compare key fields.
3. summary   — one-sentence summary in the Brain's content language, saved
               next to the note's own summary for human review.

Speed (tokens/second, load time) comes from Ollama's own timings.

Usage (on an Apple Silicon Mac with Ollama running):

    uv run python evals/local_model_quality.py ~/Projects/wooju-brain-dev \
        --models qwen3.5:4b qwen3.5:9b

Add --dry-run to print the planned requests without calling Ollama.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from brain_core.markdown import split_frontmatter
from brain_core.reader import read_records
from brain_core.schema import SourceFrontmatter

DESTINATIONS = [
    "sources",
    "wiki/concepts",
    "wiki/overviews",
    "wiki/questions",
    "wiki/how-tos",
    "wiki/mental-models",
    "memory/records",
    "memory/events",
    "memory/state",
    "projects",
    "areas",
]

CLASSIFY_SYSTEM = (
    "You file notes into a personal knowledge base with these destinations:\n"
    "- sources: what one identifiable external source (article, filing, paper) says\n"
    "- wiki/concepts: a stable definition or mechanism\n"
    "- wiki/overviews: a broad map of a topic\n"
    "- wiki/questions: an open question or an unproven derived idea\n"
    "- wiki/how-tos: a reusable procedure\n"
    "- wiki/mental-models: a reusable reasoning pattern\n"
    "- memory/records: a durable fact or preference about the user\n"
    "- memory/events: something that happened to the user, with a date\n"
    "- memory/state: the user's current situation\n"
    "- projects: work toward a finite goal\n"
    "- areas: an ongoing responsibility that links to other notes\n"
    "Answer with JSON only."
)

SOURCE_SYSTEM = (
    "Write frontmatter for a source note. Use only facts present in the note. "
    "Use 'unknown' for a published date you cannot find. Answer with JSON only."
)

SUMMARY_SYSTEM = (
    "Summarize the note in exactly one sentence of at most 80 characters, "
    "in {language}. State the main claim with its key number or date. "
    "Answer with JSON only."
)

LANGUAGE_NAMES = {"ko": "Korean", "en": "English", "ja": "Japanese"}
_HANGUL = re.compile(r"[가-힣]")
_SUMMARY_HEADINGS = ("한 줄 요약", "One-line Summary")


@dataclass
class Note:
    id: str
    path: str
    expected: str
    body: str
    frontmatter: dict[str, Any]
    own_summary: str | None


def expected_destination(path: str) -> str | None:
    parts = path.split("/")
    if parts[0] in ("sources", "projects", "areas"):
        return parts[0]
    if parts[0] in ("wiki", "memory") and len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    return None


def strip_section(body: str, headings: tuple[str, ...]) -> tuple[str, str | None]:
    """Remove the first matching '## heading' section; return (body, its text)."""
    for heading in headings:
        pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)", re.M | re.S)
        m = pattern.search(body)
        if m:
            return body[: m.start()] + body[m.end() :], m.group(1).strip()
    return body, None


def load_notes(brain: Path) -> list[Note]:
    notes = []
    for rec in sorted(read_records(brain).values(), key=lambda r: r.path):
        dest = expected_destination(rec.path)
        if dest is None:
            continue
        text = (brain / rec.path).read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        body, own = strip_section(body, _SUMMARY_HEADINGS)
        notes.append(Note(rec.id, rec.path, dest, body.strip(), fm, own))
    return notes


def content_language(brain: Path) -> str:
    try:
        import yaml

        data = yaml.safe_load((brain / "wooju-brain.yaml").read_text(encoding="utf-8")) or {}
        lang = (data.get("content") or {}).get("language", "en")
    except OSError:
        lang = "en"
    return "en" if lang in (None, "auto") else lang


class Ollama:
    def __init__(self, host: str, dry_run: bool) -> None:
        self.host = host.rstrip("/")
        self.dry_run = dry_run

    def chat(self, model: str, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        if self.dry_run:
            return {"message": {"content": "{}"}, "dry_run": True}
        try:
            return self._post(payload)
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and "think" in exc.read().decode("utf-8", "replace"):
                payload.pop("think")
                return self._post(payload)
            raise

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))


def parse_json(response: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    raw = (response.get("message") or {}).get("content", "")
    try:
        value = json.loads(raw)
        return (value if isinstance(value, dict) else None), raw
    except json.JSONDecodeError:
        return None, raw


def timing(response: dict[str, Any]) -> dict[str, float]:
    eval_count = response.get("eval_count") or 0
    eval_ns = response.get("eval_duration") or 0
    return {
        "tokens_per_second": (eval_count / (eval_ns / 1e9)) if eval_ns else 0.0,
        "total_seconds": (response.get("total_duration") or 0) / 1e9,
        "load_seconds": (response.get("load_duration") or 0) / 1e9,
    }


def hangul_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return (len(_HANGUL.findall(text)) / len(letters)) if letters else 0.0


def run_model(client: Ollama, model: str, notes: list[Note], language: str) -> dict[str, Any]:
    classify_schema = {
        "type": "object",
        "properties": {"destination": {"type": "string", "enum": DESTINATIONS}},
        "required": ["destination"],
    }
    source_schema = SourceFrontmatter.model_json_schema()
    summary_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    lang_name = LANGUAGE_NAMES.get(language, language)
    rows: list[dict[str, Any]] = []
    started = time.time()
    for note in notes:
        row: dict[str, Any] = {"path": note.path, "expected": note.expected}

        resp = client.chat(model, CLASSIFY_SYSTEM, note.body, classify_schema)
        value, raw = parse_json(resp)
        row["classify"] = {
            "answer": (value or {}).get("destination"),
            "correct": (value or {}).get("destination") == note.expected,
            "raw": raw,
            **timing(resp),
        }

        if note.expected == "sources":
            user = f"canonical_ref: {note.frontmatter.get('canonical_ref')}\n\n{note.body}"
            resp = client.chat(model, SOURCE_SYSTEM, user, source_schema)
            value, raw = parse_json(resp)
            valid, error = False, None
            try:
                SourceFrontmatter.model_validate(value or {})
                valid = True
            except ValidationError as exc:
                error = str(exc).splitlines()[0]
            row["source_fm"] = {
                "valid": valid,
                "error": error,
                "source_type_match": (value or {}).get("source_type")
                == note.frontmatter.get("source_type"),
                "published_match": str((value or {}).get("published"))
                == str(note.frontmatter.get("published")),
                "raw": raw,
                **timing(resp),
            }

        resp = client.chat(
            model, SUMMARY_SYSTEM.format(language=lang_name), note.body, summary_schema
        )
        value, raw = parse_json(resp)
        summary = (value or {}).get("summary", "")
        row["summary"] = {
            "text": summary,
            "own_summary": note.own_summary,
            "chars": len(summary),
            "within_80": 0 < len(summary) <= 80,
            "language_ok": hangul_ratio(summary) >= 0.5 if language == "ko" else True,
            **timing(resp),
        }
        rows.append(row)
        print(f"  {model} {note.path}: classify={row['classify']['answer']}", file=sys.stderr)

    def rate(values: list[bool]) -> float:
        return round(100 * sum(values) / len(values), 1) if values else 0.0

    sources = [r for r in rows if "source_fm" in r]
    speeds = [
        r[t]["tokens_per_second"]
        for r in rows
        for t in ("classify", "summary")
        if r[t]["tokens_per_second"]
    ]
    return {
        "model": model,
        "notes": len(rows),
        "wall_seconds": round(time.time() - started, 1),
        "classify_accuracy": rate([r["classify"]["correct"] for r in rows]),
        "source_fm_valid": rate([r["source_fm"]["valid"] for r in sources]),
        "source_type_match": rate([r["source_fm"]["source_type_match"] for r in sources]),
        "published_match": rate([r["source_fm"]["published_match"] for r in sources]),
        "summary_language_ok": rate([r["summary"]["language_ok"] for r in rows]),
        "summary_within_80": rate([r["summary"]["within_80"] for r in rows]),
        "median_tokens_per_second": round(statistics.median(speeds), 1) if speeds else 0.0,
        "rows": rows,
    }


def report_markdown(results: list[dict[str, Any]], brain: Path) -> str:
    lines = [
        "# Local model quality",
        "",
        f"Brain: `{brain}`",
        "",
        "| Model | Notes | Classify | Source FM valid | source_type | published "
        "| Summary language | Summary ≤ 80 | Median tok/s | Wall s |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['model']} | {r['notes']} | {r['classify_accuracy']}% "
            f"| {r['source_fm_valid']}% | "
            f"{r['source_type_match']}% | {r['published_match']}% | {r['summary_language_ok']}% | "
            f"{r['summary_within_80']}% | {r['median_tokens_per_second']} | {r['wall_seconds']} |"
        )
    for r in results:
        lines += ["", f"## {r['model']}", "", "### Misclassified", ""]
        wrong = [row for row in r["rows"] if not row["classify"]["correct"]]
        lines += [f"- `{w['path']}` → {w['classify']['answer']}" for w in wrong] or ["- none"]
        lines += [
            "",
            "### Summaries for review",
            "",
            "| Note | Model summary | Note's own summary |",
            "| --- | --- | --- |",
        ]
        for row in r["rows"]:
            own = (row["summary"]["own_summary"] or "").replace("\n", " ")
            lines.append(f"| `{row['path']}` | {row['summary']['text']} | {own} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("brain", type=Path)
    parser.add_argument("--models", nargs="+", default=["qwen3.5:4b", "qwen3.5:9b"])
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--out", type=Path, default=Path("evals/results"))
    parser.add_argument("--limit", type=int, default=0, help="Only the first N notes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    brain = args.brain.expanduser()
    notes = load_notes(brain)
    if args.limit:
        notes = notes[: args.limit]
    language = content_language(brain)
    print(f"{len(notes)} notes, content language: {language}", file=sys.stderr)

    client = Ollama(args.host, args.dry_run)
    results = [run_model(client, m, notes, language) for m in args.models]

    if args.dry_run:
        dests = sorted({n.expected for n in notes})
        print(json.dumps({"notes": len(notes), "destinations": dests}, ensure_ascii=False))
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (args.out / f"{stamp}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.out / f"{stamp}.md").write_text(report_markdown(results, brain), encoding="utf-8")
    print(f"Wrote {args.out / stamp}.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
