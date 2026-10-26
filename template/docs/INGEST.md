# Ingest and Promotion

Read this document when capturing, classifying, importing, or promoting new material into durable storage.

## Inbound workflow

`inbox/` is the default drop zone for unprocessed material.

Humans may place PDFs, books, notes, exported pages, transcripts, screenshots, or other files in `inbox/` without deciding their final destination.

The agent is responsible for inspecting the material and deciding whether it should be:

- retained in `library/`;
- summarized in `sources/`;
- synthesized into `wiki/`;
- recorded in `memory/`;
- attached to a `project/` or `area/`;
- archived;
- or discarded as not worth durable storage.

Do not treat `inbox/` as permanent storage. Processed items should leave the inbox once their durable destination is clear.

> **Humans capture to `inbox/`. Agents curate the brain.**

## Choose the knowledge-quality mode

Resolve the active mode before promoting external material into `wiki/`:

```text
explicit task request > wooju-brain.yaml > default standard
```

Use `standard` for normal low-friction ingestion. Use `rigorous` when the user requests it or when repository configuration enables it.

Both modes must preserve provenance, uncertainty, source boundaries, and meaningful conflicts. `rigorous` additionally requires the claim-verification workflow in `docs/EPISTEMICS.md`.

Do not silently switch modes because a topic merely appears important. The agent may recommend rigorous processing when false knowledge would be costly, but the configured or explicitly requested mode remains authoritative.

## Step 0 — decide whether it belongs

Before storing anything, ask:

- Will this likely matter again?
- Is it evidence, world knowledge, personal memory, project state, or area context?
- Is an existing page a better home?
- Is it sensitive enough that it should not be stored at all?

If it does not deserve durable retrieval, do not store it.

## Step 1 — identify the source or origin

For external material, identify the source precisely enough to find it again.

For personal memory, identify whether it came from the user explicitly, was confirmed later, was observed, imported, or inferred.

## Step 2 — capture only what is supported

For external sources, do not generate a supposedly complete note from a title, abstract, metadata record, search snippet, or table of contents alone.

In `standard` mode, preserve the distinction between what the source states and what the agent infers. In `rigorous` mode, identify material claims and verify them according to `docs/EPISTEMICS.md` before promoting them as durable world knowledge.

For personal memory, do not broaden a specific statement into a more general claim than the user actually made.

## Step 3 — choose the correct durable layer

- external evidence → `sources/`
- reusable knowledge about the world → `wiki/`
- durable knowledge about the user → `memory/`
- current work toward a finite outcome → `projects/`
- ongoing management context → `areas/`

Use `library/` when retaining the canonical source artifact or stable local reference is useful.

## Step 4 — update rather than duplicate

If new material changes an existing claim, personal record, event interpretation, or current state, classify the delta as:

- strengthen;
- narrow;
- contradict;
- replace;
- supersede;
- unchanged.

Prefer updating the canonical record while preserving meaningful history.

## Step 5 — connect implications and perform local synthesis

If new knowledge affects a project or area, update that context with the implication rather than duplicating the full explanation.

If a personal event changes current state, update the relevant `memory/state/` page and link back to the event when useful.

After the material has been classified and the relevant existing pages have
been read, perform the focused local synthesis pass in
[`SYNTHESIS.md`](SYNTHESIS.md):

1. Identify whether the material strengthens, narrows, contradicts, connects,
   or meaningfully extends existing knowledge.
2. If it only reorganizes existing claims, update the canonical page as
   synthesis and do not create an insight.
3. If it reveals a genuinely useful new relationship, create a `candidate`
   insight in its semantic destination with `origin: synthesis`, an allowed
   `insight_kind`, and non-empty `derived_from` links.
4. Challenge the candidate before moving it to `provisional`. Record concise
   counterpoints, scope limits, stale dependencies, and what would change the
   assessment; do not store hidden reasoning traces.
5. Keep project-specific implications in the project unless later work shows
   that they generalize.

This is a lightweight pass, not a whole-brain synthesis run. It is valid and
often preferable to find no insight. Deep synthesis occurs only on an
explicit user request.

## Step 6 — validate and log

Run relevant validators and rebuild generated indexes when needed. For a
durable insight, also check that the controlled metadata is valid, `derived_from`
is non-empty, and the page contains an explicit `## Challenge` assessment
before promotion beyond `candidate`.

Log structural changes, contradictions, supersessions, migrations, and durable decisions that future agents need to understand.

## Query-to-knowledge and query-to-memory

When a conversation, investigation, coding session, or decision produces a reusable result, use this test:

> Would the user reasonably search for this again in three months?

If yes, route it by meaning:

- stable mechanism or idea → `wiki/concepts/`
- broad map of a topic → `wiki/overviews/`
- unresolved evidence-based question → `wiki/questions/`
- reusable procedure → `wiki/how-tos/`
- reusable reasoning pattern → `wiki/mental-models/`
- durable personal fact, preference, goal, constraint, relationship, routine, or cross-project decision → `memory/records/` with an appropriate `type`
- meaningful historical occurrence → `memory/events/`
- current personal condition → `memory/state/`
- finite execution context → `projects/`
- ongoing management context → `areas/`

Do not save every answer automatically.

When information originates in conversation, keep these distinctions explicit:

- sourced external fact;
- user-provided fact;
- user preference;
- user decision;
- personal event;
- current state;
- model inference.

They are not interchangeable.
