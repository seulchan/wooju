# Wooju Brain template

This folder is the starting structure the Wooju app copies when it creates a new
Brain on your computer. A Brain is a plain folder of Markdown files that you own.

- `AGENTS.md` is the constitution that every agent working in a Brain follows.
- `docs/` holds the task-specific procedures (ingest, synthesis, memory, retrieval).
- `wooju-brain.yaml` holds Brain-level settings such as the note language.
- The empty folders are the four layers: evidence (`library/`, `sources/`),
  world knowledge (`wiki/`), personal memory (`memory/`), and action context
  (`projects/`, `areas/`), plus `inbox/` for anything not yet processed.

You do not need to edit any of this to use Wooju. The app and its agents keep the
structure for you.

Licensed under CC BY 4.0. See `LICENSE`.
