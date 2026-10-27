"""Which notes does meaning search think are alike? Used to set the thresholds.

    uv run python evals/near_pairs.py ~/Projects/wooju-brain-dev

Prints the closest note pairs and how scores spread, so SIMILAR_MIN ("similar
notes" on a note's page) and DUPLICATE_MIN ("may say the same thing") in
brain_core.retrieve can be chosen from real notes. Needs Ollama with the
embedding model; vectors go to a temporary file, never the app's own cache.
Err towards a high DUPLICATE_MIN: a missed duplicate is noticed, a false one
teaches the user to ignore the warning.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
from itertools import combinations
from pathlib import Path

from brain_core.index import BrainIndex
from brain_core.retrieve import DUPLICATE_MIN, SIMILAR_MIN, Retriever
from brain_core.vectors import VectorCache, cosine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("brain", type=Path)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    from wooju_agents.embed import EMBED_MODEL, Embedder

    embedder = Embedder()
    if not embedder.ready():
        print("The embedding model is not available in Ollama.")
        return 1
    index = BrainIndex()
    index.scan(args.brain.expanduser())
    retriever = Retriever(index)
    cache = VectorCache(Path(tempfile.mkdtemp()) / "v.sqlite", EMBED_MODEL)
    missing = retriever.load_vectors(cache)
    cache.put_many(
        [
            (k, v)
            for (k, _), v in zip(missing, embedder.documents([t for _, t in missing]), strict=True)
        ]
    )
    retriever.load_vectors(cache)

    notes = {r.id: r for r in index.all_records() if retriever.note_vector(r.id) is not None}
    pairs = sorted(
        (
            (cosine(retriever.note_vector(a), retriever.note_vector(b)), a, b)
            for a, b in combinations(sorted(notes), 2)
        ),
        reverse=True,
    )
    scores = [s for s, _, _ in pairs]
    print(f"{len(notes)} notes, {len(pairs)} pairs")
    cuts = statistics.quantiles(scores, n=20)
    print(f"median {statistics.median(scores):.2f}   90th {cuts[17]:.2f}   95th {cuts[18]:.2f}")
    print(f"now: similar from {SIMILAR_MIN}, possible duplicate from {DUPLICATE_MIN}\n")
    for score, a, b in pairs[: args.top]:
        mark = "DUP" if score >= DUPLICATE_MIN else ("sim" if score >= SIMILAR_MIN else "   ")
        print(f"  {score:.3f} {mark}  {notes[a].title}  ↔  {notes[b].title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
