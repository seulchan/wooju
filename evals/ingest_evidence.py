"""Measure the ingest agent on real files: parts, time, and key points kept.

For each file, the agent organizes a copy in a throwaway Brain with the real
model, exactly as the app does (part by part, with one fix per part). The
report shows, per file: how many parts, model calls and seconds it took, how
many key points kept their evidence and how many were left out, and whether
every quote in the note is really in the original (it must be: 100%).

The notes themselves are written next to the report so a person can judge
whether each quote actually says what its point claims.

Usage (on the Mac, with Ollama running):

    uv run python evals/ingest_evidence.py ~/Projects/wooju-brain-dev/library/* \
        --model qwen3.5:9b

Results go to evals/results/ingest-<model>-<time>/ (report.md and the notes).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from brain_core.history import ensure_repo
from wooju_agents.ingest import IngestError, IngestRun
from wooju_agents.llm import LLMError, OllamaProvider, recommended_ollama_model
from wooju_agents.text import SUPPORTED_SUFFIXES


class Counting:
    """Wraps a provider to count calls and seconds by kind of call."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.name, self.model = inner, inner.name, inner.model
        self.calls: Counter[str] = Counter()
        self.seconds: Counter[str] = Counter()

    def generate_json(self, system: str, user: str, schema: dict[str, Any], on_text=None):
        kind = schema.get("title", "?")
        start = time.monotonic()
        try:
            return self.inner.generate_json(system, user, schema)
        finally:
            self.calls[kind] += 1
            self.seconds[kind] += time.monotonic() - start


def _flat(text: str) -> str:
    return " ".join(text.replace("\\[", "[").replace("\\", "").split())


def evaluate(path: Path, provider: Any, out: Path) -> dict[str, Any]:
    counting = Counting(provider)
    with tempfile.TemporaryDirectory() as tmp:
        brain = Path(tmp)
        ensure_repo(brain)
        (brain / "inbox").mkdir()
        shutil.copy(path, brain / "inbox" / path.name)
        start = time.monotonic()
        row: dict[str, Any] = {"file": path.name}
        try:
            run = IngestRun(
                brain,
                f"inbox/{path.name}",
                counting,
                language=None,
                progress_dir=brain / ".progress",
            )
            row |= {"chars": len(run.text), "parts": len(run.parts), "truncated": run.truncated}
            while not run.finished:
                run.step()
            proposal = run.proposal()
        except (IngestError, LLMError) as exc:
            row |= {"error": f"{exc.key}: {exc}"}
            proposal = None
        row["seconds"] = round(time.monotonic() - start, 1)
        row["calls"] = dict(counting.calls)
        row["fix_calls"] = counting.calls.get("Fixes", 0)
        if proposal is None:
            return row
        note = next(c for c in proposal.changes if c.path.startswith("sources/")).content or ""
        (out / f"{path.stem}.md").write_text(note, encoding="utf-8")
        quotes = [line.split("> ", 1)[1] for line in note.splitlines() if line.startswith("  > ")]
        original = _flat(run.text)
        row |= {
            "points": sum(1 for p in run._state["parts"] for _ in p["points"]),
            "in_note": len(quotes),
            "dropped": run.dropped,
            "quotes_verbatim": sum(1 for q in quotes if _flat(q) in original),
        }
        return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--model", default=None, help="Ollama model (default: recommended)")
    args = parser.parse_args(argv)

    model = args.model or recommended_ollama_model()
    provider = OllamaProvider(model)
    if not provider.status()["model_ready"]:
        print(f"Ollama is not running or {model} is not downloaded.", file=sys.stderr)
        return 1
    files = [f for f in args.files if f.is_file() and f.suffix.lower() in SUPPORTED_SUFFIXES]
    if not files:
        print("No supported files (PDF, text, Markdown, HTML).", file=sys.stderr)
        return 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(__file__).parent / "results" / f"ingest-{model.replace(':', '-')}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for f in files:
        print(f"… {f.name}", flush=True)
        row = evaluate(f, provider, out)
        rows.append(row)
        print("  ", row, flush=True)

    lines = [
        f"# Ingest with evidence — {model}",
        "",
        "| File | Chars | Parts | Calls (fixes) | Seconds | Points kept | In note "
        "| Left out | Quotes verbatim |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(
                f"| {r['file']} | {r.get('chars', '')} | {r.get('parts', '')} "
                f"| {sum(r['calls'].values())} ({r['fix_calls']}) | {r['seconds']} "
                f"| error: {r['error']} | | | |"
            )
            continue
        lines.append(
            f"| {r['file']} | {r['chars']} | {r['parts']}{' (cut)' if r['truncated'] else ''} "
            f"| {sum(r['calls'].values())} ({r['fix_calls']}) | {r['seconds']} | {r['points']} "
            f"| {r['in_note']} | {r['dropped']} | {r['quotes_verbatim']}/{r['in_note']} |"
        )
    lines += ["", "Read each note next to this report: does every quote say what its point says?"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nNotes and report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
