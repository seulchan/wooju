# Contributing to Wooju

Thanks for helping. Read [AGENTS.md](AGENTS.md) first: it holds the rules every
change follows (the Brain is written only through proposals, user-facing text is
for non-developers, all checks pass before finishing). Settled decisions and the
reasons for them are in [docs/DECISIONS.md](docs/DECISIONS.md); what is planned
next, and what is deliberately not, is in [docs/ROADMAP.md](docs/ROADMAP.md).

## Repository layout

```text
wooju/
├── packages/brain-core/   # Brain domain model: reader, records, index, relationships
├── apps/server/           # FastAPI server: Brain index + app API (uses brain-core)
├── apps/web/              # React UI
├── apps/desktop/          # Tauri shell that runs the server as a sidecar
├── agents/                # AI providers, embeddings, capture, and agents: Ingest, Ask, Challenger
├── template/              # Brain template copied into a new Brain (CC BY 4.0)
├── samples/               # Sample notes a new user can add to look around (CC BY 4.0)
└── docs/                  # Project decisions
```

## Development

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
# Python workspace (brain-core + server) and tests
uv sync --all-packages
uv run pytest packages/brain-core agents
(cd apps/server && uv run pytest)

# Web UI
npm run web:install
npm run web:test

# Run the app locally (one server for API and UI)
npm run web:build
(cd apps/server && uv run uvicorn app.main:app)               # open http://localhost:8000
# For UI development with hot reload instead: npm run web:dev  (UI on :5173)

# Serve the Brain to Claude over MCP (stdio); the app's Settings adds this to Claude Desktop
(cd apps/server && uv run wooju-server --mcp)

# Check a Brain against the rules (errors exit 1)
uv run wooju-validate /path/to/a/brain

# Measure local model quality on a Brain (needs Ollama on this Mac)
uv run python evals/local_model_quality.py /path/to/a/brain --models qwen3.5:4b qwen3.5:9b
```

To build the Mac app (Wooju.app and a .dmg): `./scripts/build-mac.sh`.

To try it with an empty Brain, copy `template/` somewhere outside this repository
and point `WOOJU_BRAIN_PATH` at the copy.

## Where things live in the server

`apps/server/app/engine/` holds the running app, split by concern: `core`
(lifecycle, settings, writes), `capture`, `ingest`, `telegram_bot`, `search`
(meaning search, Ask, Challenger), `editing` and `thinking`. Routes are in
`apps/server/app/api/`.
