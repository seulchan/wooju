"""Measure Ask on a real Brain: does search find the right notes, and does the answer cite them?

    # Search only (no AI needed; meaning search is used if Ollama has the model):
    uv run python evals/ask_quality.py ~/Projects/wooju-brain-dev
    # Also answer every question with the local model and check the citations:
    uv run python evals/ask_quality.py ~/Projects/wooju-brain-dev --answer --model qwen3.5:9b

Questions and the notes each should rest on are in evals/ask_questions.json.
Metrics: hit@k (an expected note among the top k passages' notes), MRR, and,
with --answer, how often the answer cites an expected note, cites anything at
all, and is written in the question's language.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
import time
from pathlib import Path

from brain_core.index import BrainIndex
from brain_core.retrieve import Retriever
from brain_core.vectors import VectorCache

HERE = Path(__file__).parent


def first_rank(ids: list[str], expect: set[str]) -> int | None:
    seen: list[str] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    for rank, note in enumerate(seen, 1):
        if note in expect:
            return rank
    return None


def score(ranks: list[int | None], k: int) -> tuple[float, float]:
    hit = sum(1 for r in ranks if r is not None and r <= k) / len(ranks)
    mrr = statistics.mean(1 / r if r else 0 for r in ranks)
    return hit, mrr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("brain", type=Path)
    parser.add_argument("--questions", type=Path, default=HERE / "ask_questions.json")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--answer", action="store_true", help="also answer with the AI")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--passages", type=int, default=None, help="passages sent to the model")
    args = parser.parse_args()

    questions = json.loads(args.questions.read_text(encoding="utf-8"))["questions"]
    index = BrainIndex()
    index.scan(args.brain.expanduser())
    retriever = Retriever(index)

    from wooju_agents.embed import EMBED_MODEL, Embedder

    embedder = Embedder()
    meaning = embedder.ready()
    if meaning:
        cache = VectorCache(Path(tempfile.mkdtemp()) / "v.sqlite", EMBED_MODEL)
        missing = retriever.load_vectors(cache)
        start = time.monotonic()
        vectors = embedder.documents([t for _, t in missing])
        cache.put_many([(k, v) for (k, _), v in zip(missing, vectors, strict=True)])
        retriever.load_vectors(cache)
        print(f"indexed {len(missing)} passages in {time.monotonic() - start:.0f}s")

    rows = []
    for item in questions:
        expect = set(item["expect"])
        kw = [p.id for _, p in retriever.search(item["q"], limit=args.k)]
        row = {"q": item["q"], "keyword": first_rank(kw, expect)}
        if meaning:
            vec = embedder.query(item["q"])
            hy = [p.id for _, p in retriever.search(item["q"], limit=args.k, query_vec=vec)]
            row["hybrid"] = first_rank(hy, expect)
            row["vec"] = vec
        rows.append(row)

    def report(name: str, subset: list[dict], key: str) -> None:
        if not subset or key not in subset[0]:
            return
        hit, mrr = score([r[key] for r in subset], args.k)
        print(f"  {name:<10} hit@{args.k} {hit:5.0%}   MRR {mrr:.2f}   (n={len(subset)})")

    korean = [r for r in rows if re.search(r"[가-힣]", r["q"])]
    english = [r for r in rows if r not in korean]
    for key in ("keyword", "hybrid"):
        if key in rows[0]:
            print(f"\n{key} search")
            report("all", rows, key)
            report("Korean", korean, key)
            report("English", english, key)
    print("\nmisses:")
    for r in rows:
        missed = [k for k in ("keyword", "hybrid") if k in r and (r[k] is None or r[k] > args.k)]
        if missed:
            print(f"  [{', '.join(missed)}] {r['q']}")

    if not args.answer:
        return

    from wooju_agents.ask import ask
    from wooju_agents.llm import OllamaProvider

    provider = OllamaProvider(args.model)
    cited_expected = cited_any = right_language = 0
    times = []
    print(f"\nanswers with {args.model}:")
    for item, row in zip(questions, rows, strict=True):
        start = time.monotonic()
        answer = ask(
            index,
            item["q"],
            provider,
            language="en",
            retriever=retriever,
            query_vec=row.get("vec"),
            **({"max_passages": args.passages} if args.passages else {}),
        )
        times.append(time.monotonic() - start)
        ids = {c.id for c in answer.citations} if not answer.related_only else set()
        cited_any += bool(ids)
        cited_expected += bool(ids & set(item["expect"]))
        korean_q = bool(re.search(r"[가-힣]", item["q"]))
        korean_a = bool(re.search(r"[가-힣]", re.sub(r"\[\d+\]", "", answer.answer)))
        right_language += korean_q == korean_a or not answer.answer
        mark = "✓" if ids & set(item["expect"]) else ("·" if ids else "✗")
        print(f"  {mark} {times[-1]:5.1f}s  {item['q']}")
    n = len(questions)
    print(
        f"\n  cites an expected note {cited_expected / n:.0%}   cites anything {cited_any / n:.0%}"
        f"   question's language {right_language / n:.0%}   median {statistics.median(times):.0f}s"
    )


if __name__ == "__main__":
    sys.exit(main())
