# Knowledge Layer

Read this document before adding, editing, or synthesizing external knowledge.

The knowledge path is:

```text
library/ -> sources/ -> wiki/
```

`library/` preserves source material or stable source references. `sources/` records what an identifiable source says. `wiki/` records source-independent understanding about the world.

## `inbox/` — capture, not knowledge

Use `inbox/` for material captured but not yet classified or processed.

- Nothing in `inbox/` is authoritative.
- Do not let it become permanent storage.
- Triage items into a durable destination or delete them.
- Do not link durable wiki pages to temporary inbox files.

## `library/` — canonical source material

`library/` holds source artifacts or durable references when keeping them is useful and lawful.

Examples include PDFs, exported documentation, book notes or legally retained excerpts, repository snapshots or references, datasets, curated transcripts, and images required to interpret a source.

Do not duplicate large external resources merely to make the repository feel complete. A stable reference may be sufficient when local preservation is unnecessary.

## `sources/` — what a source says

A source note represents one identifiable source and should distinguish the source's claims from later synthesis.

Recommended frontmatter:

```yaml
---
title: "Exact source title"
source_type: paper | book | docs | spec | repo | article | video | podcast | course | conversation | experience | other
authors: []
published: YYYY-MM-DD | YYYY | unknown
accessed: YYYY-MM-DD
canonical_ref: "URL, DOI, ISBN, repo, local path, or other stable identifier"
status: active | superseded | archived
---
```

Recommended body:

```markdown
## One-line Summary
## Key Ideas
## Evidence / Examples
## Limitations / Caveats
## Useful Details
## Related Knowledge
```

Adapt the body to the source type. Do not force paper-specific sections onto code repositories, books, specifications, conversations, or personal experiments.

A source note should answer: **What does this source actually support?**

## `wiki/` — durable world knowledge

`wiki/` contains source-independent understanding synthesized across one or more sources, implementations, or experiences.

It should remain useful even if the reader does not remember the conversation that created it.

### `wiki/concepts/`

Stable definitions, mechanisms, methods, patterns, and reusable ideas.

A concept page should normally explain what it is, why it matters, how it works, a concrete example, useful boundary cases or common confusion, related concepts, and supporting sources.

### `wiki/overviews/`

Broad synthesis pages that organize a field, system, or body of knowledge. Use declarative titles, not question titles.

### `wiki/questions/`

Open or recurring questions whose answers depend on evidence, tradeoffs, or changing information.

Recommended structure:

```markdown
## Question
## Why It Matters
## What We Know
## Uncertainty / Missing Evidence
## Current Answer
## What Would Change the Answer
## Related Pages
```

When a question becomes settled and stable, move the durable result into the appropriate concept, overview, how-to, mental model, project decision, or area note.

### `wiki/how-tos/`

Reusable procedures that answer: **How do I do this reliably?**

Keep them generic enough to reuse. Project-specific runbooks stay in the project unless they generalize.

### `wiki/mental-models/`

Reusable reasoning patterns, heuristics, tradeoff frameworks, and decision lenses. Do not store one-off personal decisions here.

## Synthesis and insight

Synthesis is a reorganization, comparison, or integration of existing
knowledge that does not materially introduce a new claim. An insight is a new
relationship or abstraction derived from existing knowledge that no single
supporting source explicitly states. A source note can support the premises of
an insight without proving the relationship itself.

Use the existing semantic locations for derived insights; do not create an
`insights/` or `trusted-wiki/` layer:

- reusable general insight → the appropriate `wiki/` concept, overview, or
  mental-model page;
- unresolved evidence-seeking insight → `wiki/questions/`;
- project-specific implication → the relevant `projects/` page;
- ongoing management implication → the relevant `areas/` context.

For the durable lifecycle, controlled kinds, frontmatter, challenge step, and
local/deep synthesis procedures, read [`SYNTHESIS.md`](SYNTHESIS.md).

When an insight is durable, mark it explicitly with `origin: synthesis`, one
of the allowed `insight_kind` values, a lifecycle `status`, and non-empty
`derived_from` links. `derived_from` records the derivation path and must not
be treated as evidence that a linked page stated the derived claim. If direct
external evidence later supports the relationship, record that support
separately from the derivation provenance.

## Evidence quality

When sources differ in authority, prefer the strongest evidence appropriate to the claim:

1. specifications, standards, official documentation, source code, datasets, and original papers;
2. books and high-quality technical or professional material;
3. reputable secondary explanations;
4. exploratory material such as talks, blogs, forums, social posts, and discussions.

Lower-tier material may help with discovery or intuition, but must not silently replace stronger evidence. Source quality does not remove the need to read what the source actually supports.

Source quality and claim support are different. A strong source can contain tentative claims, and a weak source can contain a correct observation. Judge each material claim by the evidence that actually supports it.

## Knowledge-quality modes

Wooju Brain supports two levels of verification over the same durable structure:

### `standard`

Use for normal personal knowledge work. Preserve provenance, source boundaries, caveats, uncertainty, and meaningful conflicts without turning every note into a formal review workflow.

`standard` never means unverified or careless. Do not:

- treat search snippets, titles, abstracts, filenames, or AI summaries as sufficient evidence for a durable claim;
- present model inference as sourced fact;
- silently overwrite conflicting evidence;
- claim to have read material that was not actually inspected.

### `rigorous`

Use when false knowledge would be costly or when the user explicitly requests stronger verification. In addition to all `standard` rules, identify material claims, inspect the strongest appropriate evidence, search for meaningful contradiction or independent support, preserve epistemic status, and request human review only when the unresolved risk justifies it.

Read `docs/EPISTEMICS.md` for the rigorous workflow.

The active mode is resolved in this order:

```text
explicit task request > wooju-brain.yaml > default standard
```

Both modes use the same `sources/` and `wiki/`. Rigorous verification strengthens existing knowledge rather than creating a parallel trusted wiki.

## Synthesis requirement

The knowledge base should improve when new material is added.

A processed source is complete only when one of these is true:

1. it updates or supports at least one durable wiki page;
2. it materially updates personal memory, a project, or an area;
3. it is intentionally retained as a source-only record, with the reason explicit.

For material knowledge updates:

- read the relevant existing page before editing;
- identify the claim delta: `strengthen`, `narrow`, `contradict`, `replace`, or `unchanged`;
- update the body, not only the related-links list;
- preserve genuine disagreement;
- create a new page only when the idea deserves an independent retrieval target.

A collection of disconnected source summaries is not a knowledge base.

Local synthesis is useful when new material reveals a real connection,
pattern, tension, implication, or hypothesis, but ingest must not force an
insight from every source. Deep synthesis is reserved for an explicit user
request. Every durable insight is challenged before promotion, and a
project-specific implication is not silently generalized into world knowledge.

## Promotion from project experience

Generalizable knowledge discovered during a project should be promoted into `wiki/` rather than duplicated permanently inside the project.

Project-local implementation details remain in the project unless they become reusable beyond it.
