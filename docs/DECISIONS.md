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
- The recommended model is only a default. Settings lists every installed
  Ollama model, can download a suggested one or any model by name, and can
  switch to Claude or OpenAI. Files waiting for the AI resume after a switch.
- Search starts as keyword search and always works without Ollama. Semantic
  search (`qwen3-embedding:0.6b` via Ollama) is added in phase 4.

## Ask, Challenger, and the Claude connection (phase 3)

- Ask answers only from the user's own notes. Retrieval is BM25 over note
  sections with Korean particle stripping and bigrams, so it works without an
  embedding model; when results are weak the model writes extra search terms
  (other language, synonyms). Every [n] citation is checked in code and an
  answer with no valid citation is shown as "not answered by your notes".
  Ask never writes to the Brain.
- The Challenger proposes a `## Challenge` section for an insight (or a dated
  addition under an existing one), with counter-evidence linked to notes. It
  never changes `status`: promoting or rejecting stays the user's decision.
- The Claude connection is an MCP server inside the same binary
  (`wooju-server --mcp`), added to Claude Desktop's config with one click.
  Claude can search, read, and list notes, and can only *propose* notes;
  proposals from Claude are always reviewed, even ones that would be applied
  automatically if they came from the Ingest agent. Other entries in Claude's
  config are kept, the old file is backed up, and an unreadable file is never
  overwritten.

## Maintainer, meaning search, and capture (phase 4)

- The Maintainer runs when Home is shown, not on a timer and never as a
  notification: notes past `review_after` (most overdue first, with one-click
  "reviewed: in 3 months / 1 year / clear") and notes that break the rules.
- Every proposal first records the files it touches as they are, so undo
  never deletes a note written outside Wooju or discards the user's edits.
- Meaning search uses `qwen3-embedding:0.6b` through Ollama, always on this
  Mac (also when answers come from Claude or OpenAI). Vectors are cached in
  the app data folder by (model, text) hash; keyword and meaning rankings are
  fused with reciprocal rank fusion. Without the model, search is keyword-only.
- Capture: a pasted or shared link is fetched once (public http/https only)
  and becomes a source whose `canonical_ref` is the real URL. A memo is the
  user's own words: it is kept as written in `inbox/memos/` (the Brain's rules
  keep passing thoughts out of durable memory) and is searchable and askable.
- Phone: an iCloud Drive "Wooju Inbox" folder (no account or server; files are
  taken once they stop changing) and the user's own Telegram bot (token in
  the keychain, long polling while Wooju is open, one paired chat; others are
  refused). KakaoTalk has no personal bot API. The web demo is deferred.

## Running on a 16 GB Mac (found in testing)

- Ollama's default context for the embedding model reserved ~3.5 GB and,
  together with the 9B model, ran the Mac's GPU out of memory. Embeddings now
  use a 2K context, meaning-search indexing pauses while a file is organized,
  and a local model reads at most ~6K tokens of a long file (the note says so).
- All AI work goes through one lane, one task at a time: organizing a file,
  each small batch of meaning-search indexing, answering a question, and
  challenging an insight. Files are organized in arrival order; a question
  waits only for the current step. Saving a memo needs no AI and is instant.
- An out-of-memory reply from Ollama is retried once, then the file waits and
  is retried automatically (three times) instead of failing; failed files can
  be retried or removed. A link already saved is never saved twice, and a
  link already waiting is reused rather than fetched again.

## Fixing notes

- One "Edit" button, in two places: on a note (the user's own edit: applied
  at once, checked against the rules, recorded, undoable) and on a review card
  (fix what an agent proposed, then approve). Only the body is edited; the
  frontmatter is kept byte for byte. An edit never overwrites a note that
  changed elsewhere in the meantime.
- A source note records what the source says: the editor asks to fix only
  what was copied wrong, and to put disagreement under its limitations.

## Language

- Structural identifiers (frontmatter keys, controlled values, file names) are
  always English.
- Note content and UI follow the Mac's language, falling back to English, and
  can be changed in settings (`content.language: auto`).
- App messages (including server errors and change-history titles) are keyed
  and rendered in the Mac's language; history stays stored in English.

## Distribution and license

- Local desktop app first, Apple Silicon Mac first. Cloud only for an optional
  mobile inbox relay and a read-only web demo (phase 4).
- Code: Apache 2.0. Brain template: CC BY 4.0. Copyright: Seulchan Hwang.
- Desktop shell: **Tauri 2** (decided in phase 2). Small bundle, first-class
  sidecar support for the Python server, and Rust is already on the dev Mac.
  The server is frozen with PyInstaller into one sidecar binary; the window
  shows a loading page until the server answers on a free local port.
- CLA or DCO: decide before accepting outside contributions.

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
