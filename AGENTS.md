# Working on the Wooju codebase

Rules for any agent (or person) changing code in this repository. The Brain
constitution for agents working *inside a user's Brain* is `template/AGENTS.md`;
do not confuse the two.

1. Read `docs/DECISIONS.md` before changing behaviour. Do not quietly reverse a
   settled decision; propose the change instead.
2. The user's Brain is read-only to the server. Writes happen only through the
   proposal → validation → approval → git commit path.
3. Keep `packages/brain-core` framework-agnostic: no FastAPI, no HTTP models.
4. Every user-facing change is judged by one question: can a first-time,
   non-developer user do this unaided? No terminal steps, no config files.
5. Code, comments, and docs in this repository are written in English.
6. Before finishing: `uv run pytest packages/brain-core`, `(cd apps/server && uv
   run pytest)`, `uv run ruff check .`, and `npm run web:test` all pass.
