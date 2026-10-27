# Decisions

Settled decisions for Wooju, newest last. Change them deliberately and note why.

## Product

- One app, one repository. There is no separate "runtime"; this app is Wooju.
- Out of scope: notifications, calendars, sending messages. Anything that needs
  attention is shown quietly when the user opens the app.
- Top priority: no hard parts for a first-time, non-developer user. When this
  conflicts with another decision, this wins.
- Wooju is for personal knowledge management, for anyone. Investment research
  is only the domain used to validate phase 1 (the dev Brain and evals); AI
  prompts, examples, and screens stay domain-neutral.

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

## Thinking (writing in your own words)

- Principle: the AI does not write the user's thinking. It may ask, check,
  connect, and bring things back; the user writes. Research behind this:
  fully AI-written notes lowered understanding versus notes the learner had
  to integrate (Chen et al. 2025), and self-explanation, elaborative
  questions, retrieval, and spacing outperform summaries and rereading.
- Step 1: "New note" writes concepts, overviews, questions, how-tos, mental
  models, and thoughts. Wooju supplies only the folder, frontmatter, and
  headings in the Brain's language. A thought is an insight (candidate) and
  must name at least one note it rests on.
- Step 1: after a source is saved, an optional one-line takeaway in the
  user's words goes into its "내 생각 / My Takeaway" section (searchable).
- Step 2: recall before reading. A note past its review date opens with its
  title only and a box for what the user remembers; then the note, then a
  rating that spaces the next recall (well: interval doubles, at least 30
  days, at most a year; partly: same, at least 14; hardly: 7 days), stored
  as `review_interval`. Notes the user writes start with a recall in a week
  (can be turned off). Home shows the last 30 days' count, from a local log.
- Step 3: questions to think with. On request, the AI asks up to three
  questions about a note (why it holds; how it connects to a specific other
  note, found by search and checked in code; where it would not hold) and
  never answers. The user's answer goes into the note's "생각해 본 것 /
  Reflections" section, or, for a connection, becomes a thought (candidate
  insight) resting on both notes.
- Next: growing memos into notes, typed connections. Testers check steps 1–2
  before the AI-assisted steps are built.

## Conflict check

- When a source is organized, it is compared once with the most related
  passages from other sources and knowledge notes. The model reports only
  direct factual contradictions (same thing, same time, different number,
  date, or rule; different periods are explicitly not conflicts), each
  pointing at a passage that is checked in code.
- Findings go into the new note's `## Conflicts` section with links, and
  Home lists them until marked checked. The existing note is never changed;
  deciding which is right (edit or retire) is the user's call.
- The check is best effort: if it fails, the source is saved anyway. It
  costs one more model call per source and runs in the single AI lane.

## History and iCloud

- A Brain's git history lives in `.wooju-history.nosync/` with `.git` as a
  pointer file. iCloud Drive never syncs `.nosync` folders, so a Brain under
  Documents or Desktop with iCloud sync on can't have its history corrupted.
  Brains made by earlier versions are converted in place when opened; plain
  `git` keeps working on the folder.

## Fixing notes

- One "Edit" button, in two places: on a note (the user's own edit: applied
  at once, checked against the rules, recorded, undoable) and on a review card
  (fix what an agent proposed, then approve). Only the body is edited; the
  frontmatter is kept byte for byte. An edit never overwrites a note that
  changed elsewhere in the meantime.
- When a note changes, what rests on it (insights deriving from it, knowledge
  linking to it) is never rewritten automatically: a derived judgment may
  still hold, weaken, or fail. Home lists those notes as "grounds changed"
  (from history order, so notes added together never show), and the note
  page names them right after an edit. Challenging, editing, or marking a
  note as checked clears it.
- A wrong or obsolete note is retired, not deleted: `retired: date` and
  `retired_reason` are added (plus the layer's own status: source `archived`,
  insight `rejected`, memory `historical`, the old status kept for restore).
  It stays readable with its reason, is never grounds for Ask, the Challenger,
  or Claude, and what rests on it is flagged. Restore brings it back.
- A source note records what the source says: the editor asks to fix only
  what was copied wrong, and to put disagreement under its limitations.

## Language

- Structural identifiers (frontmatter keys, controlled values, file names) are
  always English.
- One language setting, in Settings > Language: the app language (screens,
  messages, Telegram replies; stored in the app's settings.json), defaulting to
  the Mac's and falling back to English. Notes are not tied to it: a new source
  note is written in its material's language, and anything added to an
  existing note (questions, takeaway, reflections, challenge, conflicts)
  follows that note's language. `content.language` in the Brain can still pin
  one language for every note; it is not shown in the app.
- App messages (including server errors and change-history titles) are keyed
  and rendered in the app language; history stays stored in English.

## Sample notes

- An empty Brain offers "Look around with sample notes": nine notes about
  remembering what you read (3 sources, 3 knowledge notes, a provisional and
  a candidate insight, a memo), in the app's language, from `samples/<lang>`.
  They are tagged `sample`, added as one undoable change, never overwrite a
  user's file, and Settings removes them again. The topic is deliberately not
  a specialist domain: the app is for anyone's knowledge.
- "Empty" means no knowledge, insight or source notes; the template's own docs
  do not count (they used to, so the empty state never showed).

## Local server safety

- The server listens on 127.0.0.1 only and answers only requests whose Host
  is the local machine (127.0.0.1, localhost, [::1]), so a web page cannot
  reach it through a name of its own pointed at 127.0.0.1 (DNS rebinding).
- No access log: search queries would otherwise sit in ~/Library/Logs/Wooju.
  The desktop app keeps server.log and rotates it past 5 MB (server.log.1).
- One copy of the app at a time: a second launch brings the first window
  forward instead of starting another server on the same Brain.

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
