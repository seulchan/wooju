# Wooju

> Drop things in. Wooju turns them into knowledge and memory you can trust, and
> brings them back with their sources when you need them.

Wooju is a local-first personal knowledge and memory app. Everything lives in a
plain folder of Markdown files on your Mac (your **Brain**). Agents sort what you
add into evidence, world knowledge, personal memory, and work context, but they
only ever **propose** changes: nothing reaches your Brain without passing
validation and, where it matters, your approval.

**Status:** early development (phase 0 of 4). Not ready for everyday use yet.

## Principles

- **No hard parts.** No terminal, no config files, no concepts to learn. If a
  first-time, non-developer user cannot do it unaided, it is a bug.
- **Local first.** Your Brain is a folder you own. The default AI runs on your Mac
  through [Ollama](https://ollama.com); OpenAI or Claude API keys are optional.
- **Propose, validate, approve.** Agents never write directly. Every change is
  checked, risk-tiered for approval, committed to git, and can be undone.

## Repository layout

```text
wooju/
├── packages/brain-core/   # Brain domain model: reader, records, index, relationships
├── apps/server/           # FastAPI server: Brain index + app API (uses brain-core)
├── apps/web/              # React UI
├── agents/                # Ingest, Challenger, Retriever, Maintainer (phase 2+)
├── template/              # Brain template copied into a new Brain (CC BY 4.0)
└── docs/                  # Project decisions
```

## Development

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# Python workspace (brain-core + server) and tests
uv sync --all-packages
uv run pytest packages/brain-core
(cd apps/server && uv run pytest)

# Web UI
npm run web:install
npm run web:test

# Run locally against a Brain folder
export WOOJU_BRAIN_PATH=/absolute/path/to/a/brain
(cd apps/server && uv run uvicorn app.main:app --reload)   # API on :8000
npm run web:dev                                             # UI on :5173
```

To try it with an empty Brain, copy `template/` somewhere outside this repository
and point `WOOJU_BRAIN_PATH` at the copy.

## License

Code: [Apache License 2.0](LICENSE). Brain template (`template/`):
[CC BY 4.0](template/LICENSE). See [NOTICE](NOTICE). "Wooju" is the project's
name and is not licensed for use by derived products.
