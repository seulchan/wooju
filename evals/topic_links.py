"""How well would the topics agent file notes into topics? Sets LINK_MIN.

    uv run python evals/topic_links.py ~/Projects/wooju-brain-dev

The answer key is the Brain itself: every note an overview already links to is
a member of that topic. Each note is matched against every overview (with the
note itself left out of the topic, so it cannot find itself), at several
thresholds. Precision matters more than recall here: a missing link is
visible and one tap away, a wrong one quietly turns a topic into noise.
Needs Ollama with the embedding model; vectors go to a temporary file.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from brain_core.index import BrainIndex
from brain_core.retrieve import Retriever
from brain_core.topics import LINK_MARGIN, LINK_MIN, is_topic
from brain_core.vectors import VectorCache, cosine

THRESHOLDS = [0.65, 0.68, 0.70, 0.72, 0.75, 0.78, 0.80]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("brain", type=Path)
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
    vectors = embedder.documents([t for _, t in missing])
    cache.put_many([(k, v) for (k, _), v in zip(missing, vectors, strict=True)])
    retriever.load_vectors(cache)
    vec = {r.id: retriever.note_vector(r.id) for r in index.all_records()}
    vec = {k: v for k, v in vec.items() if v is not None}

    topics = [r for r in index.all_records() if is_topic(r) and r.id in vec]
    gold = {
        t.id: {link.resolved_id for link in t.links if link.resolved_id} - {t.id} for t in topics
    }
    notes = [
        r
        for r in index.all_records()
        if r.id in vec and not is_topic(r) and r.category in ("source", "knowledge", "insight")
    ]
    print(
        f"{len(topics)} topics, {len(notes)} notes, "
        f"{sum(len(g) for g in gold.values())} links in the answer key\n"
    )

    def topic_vec(topic_id: str, without: str) -> list[float]:
        members = [m for m in gold[topic_id] if m != without and m in vec]
        found = [vec[topic_id], *(vec[m] for m in members)]
        total = [sum(c) for c in zip(*found, strict=True)]
        norm = sum(x * x for x in total) ** 0.5 or 1.0
        return [x / norm for x in total]

    scores = {
        n.id: sorted(
            ((cosine(vec[n.id], topic_vec(t.id, n.id)), t.id) for t in topics), reverse=True
        )
        for n in notes
    }
    print("threshold  precision  recall   links made")
    for th in THRESHOLDS:
        made = []
        for nid, ranked in scores.items():
            best = ranked[0][0] if ranked else 0
            made += [(nid, t) for s, t in ranked if s >= th and best - s <= LINK_MARGIN][:2]
        right = sum(1 for nid, t in made if nid in gold[t])
        total_gold = sum(1 for n in notes for t in topics if n.id in gold[t.id])
        p = right / len(made) if made else 1.0
        r = right / total_gold if total_gold else 0.0
        mark = "  ← now" if abs(th - LINK_MIN) < 1e-9 else ""
        print(f"  {th:.2f}      {p:6.0%}    {r:6.0%}    {len(made):4d}{mark}")

    print("\nwrong links at the current threshold:")
    for nid, ranked in scores.items():
        best = ranked[0][0] if ranked else 0
        for s, t in [x for x in ranked if x[0] >= LINK_MIN and best - x[0] <= LINK_MARGIN][:2]:
            if nid not in gold[t]:
                print(f"  {s:.3f}  {index.get(nid).title}  →  {index.get(t).title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
