# Retrieval, Freshness, and Answering

Read this document before searching the knowledge base for an answer, especially for personal, current, or mixed world-plus-user questions.

## First classify the query

Determine whether the question is primarily about:

- the world;
- the user;
- an active project;
- an ongoing area;
- or some combination.

## Retrieval priority by query type

For world-knowledge questions:

```text
wiki -> sources -> canonical source -> outside research
```

For personal-state questions:

```text
memory/state -> relevant memory/records -> memory/events -> relevant project/area
```

For preference or recommendation questions:

```text
relevant memory/records + current state + relevant wiki knowledge
```

Filter `memory/records` by semantic `type` when useful, for example `preference`, `goal`, or `constraint`.

For decision-history questions:

```text
memory/records[type=decision] -> related events -> project/area context
```

Project-local decisions should be read from the project first; consult personal memory only for decisions that remain meaningful beyond that project.

For project questions:

```text
project state -> project decisions -> relevant memory -> wiki -> sources
```

## Using derived insight

Derived insight is stored in the existing semantic destinations, not in a
separate retrieval layer. When an answer may depend on one:

- use `established` insights as derived knowledge while retaining their origin
  and `derived_from` provenance;
- include `provisional` insights or insights marked
  `epistemic.status: contested` only with their uncertainty and challenge
  limits visible;
- use `candidate` insights mainly for explicit exploration or deep synthesis,
  not as settled answers;
- exclude `rejected` and `superseded` insights from ordinary current answers
  unless the question concerns their history or failure;
- inspect the pages in `derived_from` to understand the premises, but never
  treat those links as proof that the sources stated the derived relationship.

When an answer materially relies on an insight, distinguish the
source-backed knowledge, the derived interpretation, and the remaining
uncertainty. A useful insight may guide exploration or a project experiment,
but it must not override stronger contradictory evidence. Whole-brain deep
synthesis is retrieval work only when the user explicitly requests it.

## Never infer current state from stale history

A historical event or old state record is evidence about the past, not automatic proof of the present.

Prefer records marked `current` or with recent confirmation. If freshness is unclear, state the uncertainty.

## Combine personal context with world knowledge explicitly

When answering a personalized question, distinguish:

1. what the knowledge base says generally;
2. what is known about the user's current situation;
3. the resulting recommendation or inference.

Do not collapse these into a single unsupported claim.

## Retrieve narrowly

Prefer a small set of highly relevant pages over dumping large portions of the repository into context.

## Preserve uncertainty and conflict

If pages disagree, are stale, or do not support the requested relationship, say so. Do not merge uncertainty into a falsely confident answer.

## Freshness and supersession

Use explicit dates or review metadata for content whose usefulness decays quickly, including software APIs and libraries, laws and regulations, prices and market information, schedules and availability, product specifications, medical or professional guidelines, current project state, and personal routines, preferences, and constraints that may change.

When newer evidence changes an older claim or personal state:

- update the canonical current page;
- preserve meaningful history;
- mark the old record as `historical` or `superseded` when useful;
- link to the replacing record when practical;
- record why the answer changed.

Do not equate newer with better automatically. Supersession requires evidence or an explicit user decision.

## Search methods

Use the simplest retrieval method that works:

- exact strings or identifiers → `rg` or equivalent;
- filenames and navigation → generated indexes;
- broad lexical retrieval → BM25 or equivalent;
- semantic ambiguity or cross-domain retrieval → optional vector or hybrid search.

Retrieval scores identify candidates, not truth.

Always read the relevant page before making a consequential claim from it. Read the underlying source when the wiki page is insufficient, disputed, stale, or high-stakes.

Keep machine-local indexes, caches, locks, and model artifacts outside synchronized knowledge content unless there is a specific reason to version them.
