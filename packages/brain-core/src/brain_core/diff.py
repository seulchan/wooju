"""What a proposal changes in a note that already exists, line by line.

A review card shows this instead of the agent's description of its change:
the reviewer judges the change itself. Only the body is compared; the
frontmatter's ``made_by`` line changes with every agent write and would hide
the real change.
"""

from __future__ import annotations

import difflib
from typing import Literal, TypedDict

from .markdown import split_frontmatter

Kind = Literal["add", "remove", "same", "gap"]


class DiffLine(TypedDict):
    kind: Kind
    text: str


def body_diff(old: str, new: str, *, context: int = 2, limit: int = 200) -> list[DiffLine]:
    """Changed lines with ``context`` unchanged lines around them.

    ``gap`` marks skipped unchanged lines. Empty when the bodies are equal.
    At most ``limit`` lines; a longer diff ends with a ``gap``.
    """
    a = split_frontmatter(old)[1].splitlines()
    b = split_frontmatter(new)[1].splitlines()
    out: list[DiffLine] = []
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for group in matcher.get_grouped_opcodes(context):
        if out:
            out.append({"kind": "gap", "text": ""})
        for op, a1, a2, b1, b2 in group:
            if op == "equal":
                out += [{"kind": "same", "text": line} for line in a[a1:a2]]
                continue
            out += [{"kind": "remove", "text": line} for line in a[a1:a2]]
            out += [{"kind": "add", "text": line} for line in b[b1:b2]]
    if len(out) > limit:
        out = [*out[:limit], {"kind": "gap", "text": ""}]
    return out
