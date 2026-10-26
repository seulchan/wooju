# Personal Knowledge Base

A durable personal knowledge system for what the user learns, understands, experiences, decides, builds, and wants to remember. It is designed for both direct human use and long-lived personal AI assistants such as `wooju-brain`.

Core model:

```text
Evidence            World Knowledge        Personal Memory        Action Context
--------            ---------------        ---------------        --------------
library/ -> sources/ -> wiki/               memory/                projects/ + areas/
```

The boundaries are foundational:

> **Sources record what evidence says.**  
> **Wiki records what we understand about the world.**  
> **Memory records what is known about the user.**  
> **Projects and areas record what the user is doing and managing.**

Language policy: durable knowledge is written in the language set by `content.language` in `wooju-brain.yaml`. The default `auto` follows the language of the user's Mac and falls back to English when that language is not supported. Structural identifiers (frontmatter keys, controlled values such as `type`, `status`, and `insight_kind`, and file names) are always English. Conversation may be in any language. Preserve original-language wording when translation would lose meaning.

This file is the repository constitution. Detailed procedures live in `docs/` and are binding when their task applies. Keep wording agent-neutral. If `CLAUDE.md` is used, keep it as a symlink to this file.

---

## Purpose

This repository is not a dumping ground, transcript archive, bookmark collection, or paper-only wiki. Its purpose is to turn useful inputs into durable, connected, provenance-aware knowledge and memory that remain useful months or years later.

A future reader or personal AI should be able to distinguish what is known, where it came from, whether it concerns the world or the user, when mutable information was true, whether it is still current, and how it connects to active work.

Optimize for future usefulness, not maximum capture.

---

## Startup checklist

Before making changes:

1. Re-read this file.
2. Read `wooju-brain.yaml` when present and resolve the active knowledge-quality mode.
3. Read the relevant task-specific document from `docs/` before specialized work.
4. Inspect relevant existing pages before creating a new one.
5. Check repository-local indexes, schemas, registries, or generated maps that may have changed.
6. Do not rely on memory from a previous session for mutable facts, paths, project state, or repository structure.
7. Prefer updating an existing durable page over creating a near-duplicate.
8. For personal questions, verify whether information is current, historical, or superseded before using it.

### Task-specific docs

| Task | Read first |
|---|---|
| Add or synthesize external knowledge | `docs/KNOWLEDGE.md` |
| Derive, challenge, or promote an insight | `docs/SYNTHESIS.md` |
| Perform rigorous claim verification or human review | `docs/EPISTEMICS.md` |
| Create or update personal memory | `docs/MEMORY.md` |
| Work on projects or ongoing life areas | `docs/WORK.md` |
| Ingest, classify, or promote new material | `docs/INGEST.md` |
| Search, retrieve, resolve freshness, or answer from the KB | `docs/RETRIEVAL.md` |
| Change naming, links, schemas, validators, logs, or repository mechanics | `docs/OPERATIONS.md` |

If a task crosses boundaries, read each relevant document. Do not load unrelated detail merely because it exists.

---

## Core rules

### 1. Keep evidence, world knowledge, personal memory, and action context separate

Route by meaning:

```text
External source artifact/reference    -> library/
What an identifiable source supports  -> sources/
Reusable knowledge about the world    -> wiki/
Durable knowledge about the user      -> memory/
Finite goal-oriented work             -> projects/
Ongoing management context            -> areas/
Unprocessed capture                    -> inbox/
Retired but historically useful        -> archive/
```

A source note is not automatically knowledge. A personal memory is not a general fact. A project decision is not a universal recommendation. Keep one canonical record and link to it instead of duplicating the same information across layers.

### 2. Prefer the knowledge base before outside retrieval

For material already captured here, search and read the repository first.

If the repository is insufficient and outside research is appropriate, outside sources may be used for discovery or verification. Search results are not durable knowledge by themselves: promote useful evidence into the knowledge system before changing durable claims.

### 3. Preserve provenance and epistemic status

Durable external claims must be traceable to an identifiable source or primary material. Durable personal memory must distinguish how it was obtained, such as `user_explicit`, `user_confirmed`, `observed`, `imported`, or `inferred`.

Do not present inference as explicit fact. Explicit user information outranks model inference about the user.

### 4. Treat mutable personal information as temporal

Preferences, routines, plans, employment, location, schedules, family routines, project state, and similar facts may change. Record enough temporal context to distinguish when mutable information was observed, when it was true, and when it stopped being true if known.

Within `memory/`, use folders for different lifecycles and metadata for different meanings:

```text
memory/
├── records/   # durable personal knowledge
├── events/    # append-oriented history
└── state/     # current-state projections
```

Events preserve history; state provides the latest projection. Never infer current state from stale history merely because an old record exists.

### 5. Curate durable knowledge and memory; do not merely collect

Store material a future reader would reasonably search for again. Do not save greetings, filler, duplicate explanations, raw chain-of-thought, transient status chatter, or every conversational detail.

Durable pages should connect to meaningful existing context when such a relationship exists. Do not create superficial links merely to satisfy a rule. Detailed admission, promotion, synthesis, and supersession rules live in the task-specific docs.

### 6. Preserve evidence quality

Prefer primary evidence when available. Lower-quality material may help with discovery or intuition but must not silently replace stronger evidence. Read `docs/KNOWLEDGE.md` for source-quality and synthesis rules.

### 7. Knowledge quality is configurable; truthfulness is not

The repository may operate in `standard` or `rigorous` knowledge-quality mode. `standard` minimizes friction while preserving source boundaries, provenance, uncertainty, and abstention. `rigorous` adds material-claim verification, contradiction search, epistemic status, and risk-based human review.

An explicit task request overrides repository configuration; repository configuration overrides the default `standard` mode. Quality mode may change the depth of verification, but never permits fabricated support, hidden inference, or silent resolution of meaningful evidence conflicts.

Read `docs/EPISTEMICS.md` whenever rigorous verification is active.

### 8. Do not fabricate completeness

If the user asks for all, exhaustive, complete, or comprehensive coverage, track the full set and report checked, excluded, failed, and unresolved items explicitly. Sampling is acceptable only when labeled as sampling.

### 9. Protect sensitive information

Do not store secrets, credentials, authentication material, private keys, recovery codes, government identifiers, financial account numbers, or similarly sensitive material in the knowledge graph.

Minimize highly private personal detail even when relevant. The goal is useful memory, not exhaustive surveillance.

### 10. Scripts do mechanics; agents do judgment

Use deterministic scripts for extraction, validation, indexing, normalization, duplicate detection, migrations, and other repeatable mechanics.

Do not delegate semantic reading, synthesis, personal interpretation, or durable memory creation to an opaque batch process without reviewable evidence.

### 11. Preserve uncertainty, disagreement, and history

Do not collapse conflicting evidence, stale information, or model inference into a falsely confident current claim. When newer evidence changes knowledge or personal state, update the canonical current representation while preserving meaningful history and supersession links where useful.

### 12. Keep synthesis distinct from sourced fact

Synthesis reorganizes or compares existing knowledge without materially adding a claim. An insight is a newly derived relationship or abstraction and is not source-backed fact merely because its premises are. Every durable derived insight preserves `origin: synthesis`, an allowed `insight_kind`, a lifecycle `status`, and non-empty `derived_from` provenance; `derived_from` records derivation, not proof. Challenge an insight before promoting it. Candidate and provisional insights must not be presented as settled knowledge, and project-specific implications stay in project context unless they genuinely generalize.

---

## Repository map

```text
personal-kb/
├── AGENTS.md              # constitution
├── wooju-brain.yaml       # repository-level behavior settings
├── docs/                  # task-specific operating manuals
├── inbox/                 # unprocessed capture
├── library/               # retained source artifacts/references
├── sources/               # source-grounded notes
├── wiki/                  # durable world knowledge
├── memory/                # durable personal memory
├── projects/              # finite goal-oriented work
├── areas/                 # ongoing management context
├── logs/                  # meaningful change history
├── scripts/               # deterministic mechanics
├── index.md + indexes/    # generated navigation
└── archive/               # retired but useful material
```

Do not create folders merely because a category might exist. Add structure when real content requires it. Detailed schemas, naming, link, validation, and index rules live in `docs/OPERATIONS.md`.

---

## Final check before writing durable content

Before creating or changing a durable record, ask:

1. **Layer:** Is this evidence, world knowledge, personal memory, project state, or area context?
2. **Support:** What source, user statement, event, or observation supports it?
3. **Time:** If mutable, is its current/historical status explicit enough?
4. **Canonical home:** Am I updating the right existing record rather than duplicating it?
5. **Connection:** Does it affect an existing concept, state, project, area, or decision?
6. **Uncertainty:** Am I preserving inference, disagreement, and missing evidence instead of hiding them?
7. **Quality:** Am I applying the active `standard` or `rigorous` knowledge-quality mode correctly?
8. **Procedure:** Have I read the relevant task-specific document before applying detailed rules?

When in doubt, preserve the distinction between **evidence, world knowledge, personal memory, action context, inference, event, and current state**.
