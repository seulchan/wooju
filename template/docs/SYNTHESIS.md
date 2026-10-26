# Synthesis and Insight Lifecycle

Read this document when deriving, challenging, promoting, retrieving, or
reviewing a relationship that is not directly stated by one identifiable
source. It extends the existing `library/` → `sources/` → `wiki/` path; it does
not create another knowledge store.

## Purpose and boundary

Wooju Brain can reorganize accumulated knowledge and derive useful
relationships from it. That capability must remain visibly different from
recording what a source says:

### Synthesis

Synthesis is the reorganization, comparison, or integration of existing
knowledge without materially introducing a new claim.

Examples:

- comparing several approaches to agent memory;
- combining several source notes into an overview;
- organizing the tradeoffs already described across existing pages.

Synthesis normally belongs in the appropriate existing wiki or project page.

### Insight

An insight is a newly derived relationship or abstraction that is not
explicitly stated by any one supporting source. It may be useful and well
reasoned while still being an inference from its premises.

The supporting pages may establish the premises without proving the derived
relationship. A derived insight must therefore remain labeled as derived even
when it later becomes established for the stated scope.

Do not store hidden reasoning traces. Record the concise result, its
derivation, the material objections, and what would change the assessment.

## Insight kinds

Use only these initial kinds:

| Kind | Meaning |
| --- | --- |
| `pattern` | A structure or principle recurring across multiple pieces of knowledge. |
| `connection` | A meaningful relationship between concepts that were previously separate. |
| `tension` | Two supported principles or observations that pull in different directions. |
| `implication` | What existing knowledge suggests for a problem, project, or decision. |
| `hypothesis` | A plausible new claim that still requires stronger validation. |

Do not expand this taxonomy in v1. If an idea does not fit one of these kinds,
keep it as ordinary synthesis, an open question, or a transient discussion.

## Where insights live

There is deliberately no `insights/`, `trusted-wiki/`, or other parallel
knowledge layer. Route an insight by meaning:

| Meaning | Durable destination |
| --- | --- |
| Reusable general concept or pattern | The appropriate page in `wiki/concepts/` or `wiki/overviews/`. |
| Reusable reasoning abstraction | `wiki/mental-models/`. |
| Unresolved evidence-seeking idea | `wiki/questions/`. |
| Project-specific implication or decision | The relevant `projects/{project}/` page, usually a decision, experiment, or note. |
| Ongoing management implication | The relevant `areas/` context, with canonical knowledge linked from it. |

Generalize a project implication into `wiki/` only when it is genuinely
reusable beyond that project. Do not duplicate the same insight in both
locations; link from the project or area to the canonical page when a
generalization exists.

A candidate that is not worth durable retrieval can remain in the review
conversation and need not become a file. If it is stored, it uses the semantic
destination where it belongs and remains visibly non-established.

## Durable representation

Every durable derived insight has inspectable derivation provenance. Use the
repository's existing frontmatter conventions and add only the fields needed
to identify the synthesis:

```yaml
---
title: "Bounded attention across memory and tools"
origin: synthesis
insight_kind: connection
status: candidate
derived_from:
  - "[[concepts/context-window-management]]"
  - "[[concepts/tool-selection]]"
---
```

For a wiki page, wikilinks follow the wiki-root convention in
`docs/OPERATIONS.md`. For a project, source, or area page, use the repository's
normal cross-root Markdown-link convention when a wikilink would be ambiguous.

For a durable insight:

- `origin: synthesis` identifies the page as derived rather than a direct
  source note;
- `insight_kind` uses one of the five controlled kinds above;
- `status` records the insight lifecycle below;
- `derived_from` is non-empty and records the pages, source notes, project
  context, or observations that led to the idea.

`derived_from` is a derivation trail, not a proof field. Do not cite a page as
explicitly stating the insight merely because it appears in `derived_from`.

Keep direct support separate in the body when it exists. A useful durable
shape is:

```markdown
## Insight

One concise statement of the derived relationship.

## Why It May Matter

What this could improve, explain, or make possible.

## Directly Supported Premises

- `[[...]]` supports the first premise within its stated scope.
- `[[...]]` supports the second premise within its stated scope.

## Supporting Evidence

Sources that directly support the relationship, if any. If none do, say so
plainly; the relationship remains a synthesis even when its premises are
source-backed.

## Challenge

- What would make this wrong?
- Counterexamples or meaningful contradictions:
- Scope limits, analogy risks, or overreach:
- Stale or superseded dependencies:
- Is this genuinely new, or only a restatement?

## Assessment

- Current status:
- What would change the status:

## Destination and Use

How this should affect retrieval, a project, an experiment, or a decision.
```

The challenge is a concise semantic assessment, not a transcript of hidden
reasoning. A durable insight should not be promoted past `candidate` without
an explicit challenge result.

## Lifecycle

The lifecycle is intentionally a small convention, not a workflow engine:

```text
existing knowledge or project context
              ↓
       derive candidate
              ↓
           challenge
       ↙                ↘
   rejected          refine
                        ↓
                  provisional
                        ↓
          additional support or testing
                        ↓
                   established
                        ↓
             superseded when replaced
```

The lifecycle meanings are:

- `candidate` — a newly derived idea under review. It is not a settled fact
  and should not silently drive ordinary retrieval answers.
- `provisional` — it survived a challenge, but its support, scope, or testing
  is still incomplete. It may remain provisional indefinitely.
- `established` — the relationship has passed the relevant challenge and has
  adequate additional support, testing, or repeated usefulness for its stated
  scope. It is still derived; this status does not mean a source explicitly
  stated the relationship.
- `rejected` — challenge found the idea unsupported, unhelpful, redundant, or
  too broad. Preserve it only when its history is useful; otherwise do not
  create a durable page for it.
- `superseded` — a later insight or decision replaces it. Preserve the original
  derivation and link the replacement when one exists.

`candidate`, `provisional`, and `established` are the normal lifecycle states.
`rejected` and `superseded` are historical outcomes, not active retrieval
states. No automatic transition is implied by the presence of more links or
more text.

## Challenge before promotion

Insight generation must be followed by an explicit challenge before promotion
from `candidate` to `provisional`, and again when material new evidence is
needed for `established`. The agent performing synthesis makes this semantic
judgment; no critic agent or debate simulation is required.

At minimum, check:

- What observation, evidence, or test would make the insight wrong?
- Is the relationship more than an analogy or a metaphor?
- Is the conclusion broader than the premises support?
- Are there meaningful counterexamples?
- Does existing knowledge contradict it?
- Is one weak or indirect source carrying too much of the conclusion?
- Is the idea actually new synthesis, or just a restatement of an existing
  page?
- Does it depend on stale, superseded, or scope-mismatched knowledge?

Record the material objections and the resulting scope or next test. Do not
invent certainty to make the page look complete. If the challenge finds a
contradiction, preserve the tension or use a provisional/contested assessment
instead of silently choosing a side.

## Local synthesis during ingest

Local synthesis is the inexpensive synthesis pass that accompanies normal
ingest. It is not a whole-repository scan and it must not force an insight from
every source.

After classifying and reading the relevant material:

1. Inspect the most relevant existing durable pages before creating anything.
2. Identify whether the new material `strengthens`, `narrows`, `contradicts`,
   `connects`, or meaningfully extends existing knowledge.
3. If the result is only a reorganization or comparison, update the canonical
   page as synthesis and stop.
4. If a genuinely useful new relationship appears, derive a `candidate`
   insight with `derived_from` links and run the challenge step.
5. Refine it to `provisional`, reject it, or leave it as a review item. Do not
   make it `established` merely because the source was processed.
6. Route the result to `wiki/`, a project, an area, or `wiki/questions/` by
   meaning. Keep project implications project-local unless they generalize.

Routine ingest remains complete when no insight is found. The source may still
update a wiki page, memory, project, or area, or be intentionally retained as a
source-only record under `docs/KNOWLEDGE.md`.

## Deep synthesis on explicit request

Deep synthesis is invoked by an explicit user request, such as asking for new
insights from all stored knowledge about agent architecture. It may retrieve
multiple relevant clusters and compare them across domains, but it does not run
continuously after every ingest.

The process is:

1. Define the requested topic, scope, and intended use.
2. Retrieve a narrow but meaningfully diverse set of relevant wiki pages,
   source notes, and project context.
3. Generate possible patterns, connections, tensions, implications, and
   hypotheses.
4. Challenge the strongest candidates and discard restatements, weak
   analogies, and ideas that do not change understanding or action.
5. Present useful candidates to the user before durable promotion when review
   would affect their destination, usefulness, or application.
6. On the user's direction, promote, keep provisional, investigate, or discard
   each candidate. A promoted insight still carries its derivation and
   challenge record.

Do not rank candidates with numeric novelty or confidence scores. Select them
qualitatively for usefulness, scope, distinctness, and the value of the
question or action they enable.

A compact review packet is enough:

```text
Candidate insight

Kind:
connection

Insight:
...

Derived from:
- ...
- ...

Why this may matter:
...

Challenge / counterpoints:
...

Current status:
candidate

Suggested destination:
...

Recommended next step:
...
```

The useful human decision is whether to preserve, investigate, or apply the
idea, not whether the human can serve as a domain truth oracle.

## Standard and rigorous modes

Synthesis uses the existing `standard` / `rigorous` quality modes. It does not
introduce a second mode or a separate promotion system.

In `standard` mode:

- preserve `origin`, `insight_kind`, `status`, and `derived_from`;
- perform and record the challenge step;
- keep direct support, derivation, and uncertainty distinct;
- avoid formal claim-by-claim verification unless the task warrants it.

In `rigorous` mode, apply `docs/EPISTEMICS.md` to material world claims:

- inspect the strongest relevant evidence and meaningful counterevidence;
- state the exact premises and scope rather than verifying a broader claim;
- keep direct source support separate from `derived_from`;
- use the existing nested `epistemic` metadata when it improves retrieval and
  review.

The top-level `status` on an insight is its lifecycle status. A nested
`epistemic.status`, when used in rigorous mode, is the existing assessment of
the material claim (`established`, `provisional`, or `contested`). They answer
different questions and must not be collapsed. A candidate may have no
epistemic assessment yet; a provisional insight may be epistemically
provisional or contested. An established lifecycle state still requires the
relationship to remain visibly derived unless direct evidence explicitly
supports it.

When no source explicitly states the synthesized relationship, say that the
sources support the premises and that the relationship is an agent-derived
interpretation. Strong source quality does not remove this distinction.

## Retrieval behavior

Derived insight should improve reasoning without becoming an unquestioned
premise:

- retrieve `established` insights as useful derived knowledge, while retaining
  their derived label and provenance;
- retrieve `provisional` insights or insights marked
  `epistemic.status: contested` when relevant, but surface the uncertainty and
  challenge that limits them;
- use `candidate` insights mainly for explicit exploration or deep synthesis,
  not as settled answers;
- exclude `rejected` and `superseded` insights from ordinary current answers
  unless the question is about their history or failure;
- follow `derived_from` to inspect the premises and supporting sources, but do
  not treat those links as proof of the relationship.

When an answer depends materially on an insight, distinguish the source-backed
knowledge, the derived interpretation, and the remaining uncertainty. A useful
insight may guide exploration or a project experiment, but it must not override
stronger contradictory evidence.

## Synthetic validation scenarios

These scenarios validate the rules without adding synthetic pages to the
knowledge base. In each case, the premises may be directly supported while the
relationship remains derived.

### A — connection

**Stored knowledge**

- Long-running agents suffer when too much historical context remains active.
- Exposing too many tools can make tool selection harder.

**Derived**

Memory retrieval and tool visibility may both be instances of bounded
attention allocation.

**Directly supported**

The two stored observations, each within its own scope.

**Still inference**

That the mechanisms share a useful abstraction and should be analyzed through
one attention boundary. Neither premise is being cited as explicitly stating
that relationship.

**Appropriate status**

`candidate` immediately after derivation; `provisional` after a challenge if
the abstraction remains useful. It should not become `established` without
tests, stronger cross-domain support, or repeated successful application.

**Destination**

`wiki/mental-models/` if reusable beyond one project; otherwise keep it in the
relevant project context.

**What could change it**

Evidence that the two effects arise from unrelated constraints, or a
counterexample where increasing active history and tool visibility behave
independently under the intended scope, would narrow or reject the insight.

### B — tension

**Stored knowledge**

- More retained memory improves continuity.
- More retrieved context can increase noise and degrade attention.

**Derived**

Memory systems face a retention-versus-retrieval tension: preserving more
information and showing more information are different optimization problems.

**Directly supported**

The continuity benefit of retention and the noise cost of retrieved context,
within the scopes of the two observations.

**Still inference**

That the distinction should structure memory design and that the two goals
should be optimized separately. The premises do not select one universal
retention or retrieval policy.

**Appropriate status**

`provisional` after challenge, with the tension preserved rather than resolved.
It may become `established` as a scoped mental model if independent evidence or
repeated design use supports it; it may remain provisional indefinitely.

**Destination**

`wiki/mental-models/` or a reusable `wiki/concepts/` page, with links to the
relevant source-backed premises.

**What could change it**

Evidence that retention and retrieval volume cannot be usefully separated for
the target system, or a meaningful counterexample to the attention cost, would
force a narrower formulation or rejection. A new result could also supersede
the model without erasing its history.

### C — project implication

**Stored knowledge**

- General knowledge: availability should not imply visibility.
- Project context: Wooju has tools, artifacts, and durable memory competing for
  a bounded model context.

**Derived**

Wooju may benefit from applying one attention boundary to decide which
capabilities and memories become cognitively visible.

**Directly supported**

The general availability/visibility distinction and the project's bounded
context constraint.

**Still inference**

That a shared attention boundary is the right Wooju design, rather than
separate ranking or visibility policies.

**Appropriate status**

`candidate` until the project team accepts it as a useful design question;
`provisional` after a scoped architecture experiment or review. It is not an
established universal fact merely because it is plausible.

**Destination**

The relevant `projects/{wooju-project}/` design decision, experiment, or note.
Do not copy it into `wiki/` unless later work shows that the principle
generalizes beyond Wooju.

**What could change it**

A project experiment showing that a shared boundary harms tool use or memory
retrieval, or evidence that the resources require incompatible visibility
policies, would narrow, reject, or supersede the implication.

## Deferred by design

This first version intentionally does not add:

- an insight database or separate insight store;
- a graph engine or graph query language;
- numeric confidence, novelty, or ranking scores;
- automatic whole-brain background synthesis;
- a multi-agent critic or debate loop;
- a second quality-mode configuration surface;
- claim objects for every wiki sentence;
- a separate trusted wiki.

Plain Markdown, small frontmatter conventions, semantic placement, and an
explicit challenge step are sufficient until real usage demonstrates a need
for more machinery.
