"""The Claude connection: Wooju's Brain as an MCP server for Claude Desktop.

Claude starts this as ``wooju-server --mcp`` (stdio). It can search and read
the Brain, and it can *propose* notes. A proposal is never written directly:
it waits in Wooju's Review page until the user approves it, exactly like the
Ingest agent's work. stdout belongs to the MCP protocol, so nothing else may
print to it; logs go to stderr.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from brain_core.changes import FileChange, Proposal, ProposalStore, approval_for
from brain_core.index import BrainIndex
from brain_core.markdown import split_frontmatter
from brain_core.retrieve import RetrieverCache
from brain_core.schema import SCHEMAS, layer_for

logger = logging.getLogger("wooju.mcp")

RESCAN_SECONDS = 5.0
_PROPOSABLE = ("sources", "wiki", "memory", "projects", "areas")

INSTRUCTIONS = """\
Wooju is the user's personal knowledge Brain: Markdown notes on their Mac.

Layers: sources/ (what one source says), wiki/ (durable knowledge: concepts,
overviews, questions), insights (origin: synthesis; derived hypotheses with a
status: candidate < provisional < established; never treat them as facts),
memory/ (the user's own preferences, decisions, and history), projects/ and
areas/ (ongoing work). A note with `retired` was judged wrong or obsolete by the
user (see `retired_reason`): it never appears in search; don't rely on it.

When answering from the Brain: search first, read the notes you rely on, and
cite them by title. Say when the Brain does not contain the answer. Prefer
sources and wiki over insights, and mention an insight's status if you use one.

Writing: use propose_note. Nothing is saved until the user approves it in the
Wooju app (Review). Follow the Brain's conventions: YAML frontmatter, English
structural keys, a source note needs source_type and canonical_ref, an insight
needs origin: synthesis, insight_kind, status: candidate, derived_from, and a
'## Challenge' section before it can be promoted.
"""


class BrainView:
    """The Brain's index for this process, rescanned when it may be stale.

    Meaning search reuses the vectors the Wooju app has already computed (it
    never indexes on its own) and embeds only the query, when Ollama is there.
    """

    def __init__(self, brain: Path, embedder: Any = None) -> None:
        self.brain = brain
        self.index = BrainIndex()
        self.retrievers = RetrieverCache()
        self.embedder = embedder
        self._scanned = 0.0

    def fresh(self) -> BrainIndex:
        if time.monotonic() - self._scanned > RESCAN_SECONDS:
            self.index.scan(self.brain)
            self._scanned = time.monotonic()
        return self.index

    def search(self, query: str, limit: int) -> list[tuple[float, Any]]:
        index = self.fresh()
        retriever = self.retrievers.get(index)
        query_vec = None
        if self.embedder is not None:
            try:
                if retriever.pending is None:
                    from brain_core.changes import data_dir
                    from brain_core.vectors import VectorCache

                    cache = VectorCache(
                        data_dir() / "search" / "vectors.sqlite", self.embedder.model
                    )
                    retriever.load_vectors(cache)
                if retriever.vector_coverage[0]:
                    query_vec = self.embedder.query(query)
            except Exception:  # noqa: BLE001 — meaning search is optional
                logger.info("Meaning search unavailable; using keywords")
        return retriever.search(query, limit=limit, query_vec=query_vec)


def _note_id(value: str) -> str:
    value = value.strip().strip("[]").split("|")[0].split("#")[0].strip()
    return value[:-3] if value.endswith(".md") else value


def check_proposal(brain: Path, path: str, content: str) -> str | None:
    """Why this note can't be proposed, or None. Mirrors the validator's schema rules."""
    rel = PurePosixPath(path)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        return "Use a path inside the Brain, like wiki/concepts/korea-discount.md."
    if rel.parts[0] not in _PROPOSABLE:
        return f"Notes go under one of: {', '.join(_PROPOSABLE)}."
    if rel.suffix != ".md" or not re.fullmatch(r"[A-Za-z0-9._/-]+", path):
        return "Use a lowercase English file name ending in .md, like overviews/value-up.md."
    frontmatter, body = split_frontmatter(content)
    if not frontmatter:
        return "Start the note with YAML frontmatter (--- ... ---) that has at least a title."
    layer = layer_for(rel.parts, frontmatter)
    schema = SCHEMAS.get(layer or "")
    if schema is not None:
        try:
            schema.model_validate(frontmatter)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(x) for x in e['loc']) or 'frontmatter'}: {e['msg']}"
                for e in exc.errors()
            )
            return f"The frontmatter doesn't fit the {layer} rules: {problems}"
    if not body.strip():
        return "The note has no body."
    return None


def build_server(  # noqa: ANN201
    brain: Path, store: ProposalStore | None = None, embedder: Any = None
):
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations

    view = BrainView(brain, embedder)
    store = store or ProposalStore()
    server = MCPServer(name="wooju", title="Wooju Brain", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

    @server.tool(annotations=read_only)
    def search_brain(query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search the user's Brain with a question or keywords (Korean or English).

        Returns the best-matching passages with the note id to pass to read_note.
        """
        hits = view.search(query, max(1, min(limit, 20)))
        return [
            {
                "id": p.id,
                "title": p.record.title,
                "kind": p.record.category,
                "status": p.record.status,
                "section": p.heading,
                "text": p.text,
                "score": round(score, 2),
            }
            for score, p in hits
        ]

    @server.tool(annotations=read_only)
    def read_note(id: str) -> dict[str, Any]:  # noqa: A002 — the MCP argument name
        """Read one note in full: frontmatter, body, and its links."""
        index = view.fresh()
        record = index.get(_note_id(id))
        if record is None:
            raise ToolError(f"No note with id {id!r}. Use search_brain or list_notes to find ids.")
        return {
            "id": record.id,
            "path": record.path,
            "title": record.title,
            "kind": record.category,
            "status": record.status,
            # Retired notes are wrong or obsolete: never use them as grounds.
            "retired": record.retired,
            "frontmatter": record.metadata,
            "content": record.content,
            "links": [link.resolved_id or link.target for link in record.links],
            "derived_from": [r.resolved_id or r.ref for r in record.derived_from_resolved],
            "modified_at": record.modified_at,
        }

    @server.tool(annotations=read_only)
    def list_notes(kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List notes, newest first. kind: source, knowledge, insight, memory, project, area."""
        index = view.fresh()
        records = [r for r in index.recent(100) if kind is None or r.category == kind]
        return [
            {
                "id": r.id,
                "title": r.title,
                "kind": r.category,
                "status": r.status,
                "modified_at": r.modified_at,
            }
            for r in records[: max(1, min(limit, 100))]
        ]

    @server.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
        )
    )
    def propose_note(path: str, content: str, reason: str) -> dict[str, Any]:
        """Propose a new or updated note. The user approves it in the Wooju app before
        anything is saved.

        path: Brain-relative, e.g. "wiki/concepts/korea-discount.md".
        content: the whole Markdown file including YAML frontmatter.
        reason: one sentence for the user's review card, in the user's language.
        """
        problem = check_proposal(view.brain, path, content)
        if problem:
            raise ToolError(problem)
        exists = (view.brain / path).exists()
        changes = [FileChange(op="write", path=path, content=content)]
        approval = approval_for(changes)
        if approval == "auto":
            approval = "batch"  # anything from outside the app is always reviewed
        frontmatter, _ = split_frontmatter(content)
        title = str(frontmatter.get("title") or PurePosixPath(path).stem)
        proposal = store.save(
            Proposal(
                agent="claude",
                origin=path,
                title=f"Claude: {title}",
                summary=reason.strip(),
                changes=changes,
                approval=approval,
            )
        )
        return {
            "proposal_id": proposal.id,
            "status": "waiting_for_approval",
            "updates_existing_note": exists,
            "message": "Saved for review. The user approves or rejects it in Wooju → Review.",
        }

    return server


def run_stdio() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    from .config import resolve_brain_path

    brain = resolve_brain_path()
    if brain is None or not brain.is_dir():
        print(
            "Wooju has no Brain folder yet. Open the Wooju app and choose one first.",
            file=sys.stderr,
        )
        sys.exit(1)
    from wooju_agents.embed import EMBED_MODEL, Embedder

    from .settings import load

    embedder = Embedder(EMBED_MODEL, host=load().ai.ollama_host)
    build_server(brain, embedder=embedder if embedder.ready() else None).run("stdio")
