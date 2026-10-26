"""Embedding vectors for passages, cached on disk outside the Brain.

Vectors are keyed by a hash of (model, passage text), so an unchanged passage
is never embedded twice and an edited one simply gets a new key. The cache is
a small SQLite file in the app's data folder; deleting it only costs time.
Nothing here calls a model: callers pass vectors in (see wooju_agents.llm).
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from array import array
from collections.abc import Iterable, Sequence
from operator import mul
from pathlib import Path

try:
    from math import sumprod as _dot  # Python 3.12+
except ImportError:  # pragma: no cover

    def _dot(a: Sequence[float], b: Sequence[float]) -> float:
        return sum(map(mul, a, b))


def normalize(vec: Sequence[float]) -> array:
    norm = math.sqrt(_dot(vec, vec)) or 1.0
    return array("f", (x / norm for x in vec))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product of two normalized vectors."""
    return _dot(a, b)


class VectorCache:
    def __init__(self, path: Path, model: str) -> None:
        self.path = path
        self.model = model
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vec BLOB)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}\0{text}".encode()).hexdigest()

    def get_many(self, keys: Iterable[str]) -> dict[str, array]:
        keys = list(dict.fromkeys(keys))
        out: dict[str, array] = {}
        with self._connect() as db:
            for start in range(0, len(keys), 500):
                chunk = keys[start : start + 500]
                marks = ",".join("?" * len(chunk))
                for key, blob in db.execute(
                    f"SELECT key, vec FROM vectors WHERE key IN ({marks})", chunk
                ):
                    vec = array("f")
                    vec.frombytes(blob)
                    out[key] = vec
        return out

    def put_many(self, items: Iterable[tuple[str, Sequence[float]]]) -> None:
        rows = [(key, normalize(vec).tobytes()) for key, vec in items]
        with self._connect() as db:
            db.executemany("INSERT OR REPLACE INTO vectors (key, vec) VALUES (?, ?)", rows)
