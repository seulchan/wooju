# Decisions

Settled decisions for Wooju, newest last. Change them deliberately and note why.

## Product

- One app, one repository. There is no separate "runtime"; this app is Wooju.
- Out of scope: notifications, calendars, sending messages. Anything that needs
  attention is shown quietly when the user opens the app.
- Top priority: no hard parts for a first-time, non-developer user. When this
  conflicts with another decision, this wins.
- Phase 1 validation domain: investment research.

## Architecture

- The Brain (Markdown + git) is the single source of truth, kept outside this
  repository in a folder the user owns.
- Agents only propose changes. Proposals are validated, then approved by risk:
  sources are applied automatically, knowledge edits are approved in batches,
  personal memory and insight promotion are always approved one by one.
- Python and git are bundled with the app; users never install them.

## AI

- Default: Ollama on the user's Mac. Optional: the user's own OpenAI or Claude
  API key, stored in the OS keychain, never in the Brain or logs.
- The app does not install Ollama. It opens the download page and detects the
  install when it finishes.
- Baseline hardware: Apple Silicon (M1). 8 GB → `qwen3.5:4b`; 16 GB+ →
  `qwen3.5:9b`. Gemma 4 E4B was evaluated and not chosen (Korean, long
  context, and text tasks favour Qwen). Re-check with real notes in phase 1.
- Measured in phase 1 (see `docs/PHASE-1-FINDINGS.md`): 9B files 76% of notes
  correctly, 4B 69%. Model output is never filed without approval, and the
  source-vs-memory decision is made from the item's origin, not by the model.
- Search starts as keyword search and always works without Ollama. Semantic
  search (`qwen3-embedding:0.6b` via Ollama) is added in phase 4.

## Language

- Structural identifiers (frontmatter keys, controlled values, file names) are
  always English.
- Note content and UI follow the Mac's language, falling back to English, and
  can be changed in settings (`content.language: auto`).

## Distribution and license

- Local desktop app first, Apple Silicon Mac first. Cloud only for an optional
  mobile inbox relay and a read-only web demo (phase 4).
- Code: Apache 2.0. Brain template: CC BY 4.0. Copyright: Seulchan Hwang.
- Desktop shell (Tauri or Electron): decide in phase 2. CLA or DCO: decide
  before accepting outside contributions.

## Roadmap

0. Monorepo, brain-core extraction, license change. Gate: all existing tests pass.
1. Schemas and validators, 20–30 real investment-research notes, Qwen quality
   check. Gate: zero validator errors; list of ambiguous classifications.
2. Easy first run: installer, folder-only setup, Ollama connection, drag and
   drop, approval cards, Ingest agent. Gate: three non-developers reach their
   first saved item unaided within three minutes.
3. Ask and connect: in-app questions, one-click Claude connection (MCP), history
   and undo, Challenger. Gate: a non-developer gets a sourced answer from their
   own material.
4. Expansion: mobile and messenger capture, hybrid search, scheduled Maintainer
   with review dates, web demo.
