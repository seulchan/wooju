# Epistemic Quality and Rigorous Verification

Read this document when `knowledge.quality_mode` is `rigorous`, when the user explicitly requests rigorous verification, or when reviewing a material knowledge conflict.

The goal is not to make the human a truth oracle. The goal is to make evidence, uncertainty, disagreement, and the agent's reasoning boundary inspectable enough that a non-expert can safely decide how the knowledge should be handled.

## Core principles

1. **The human is not the oracle of truth.** Human review approves handling, escalation, or continued investigation; it does not require the reviewer to already know the answer.
2. **Uncertainty is durable information.** Preserve it instead of forcing every claim into true or false.
3. **Source quality is not claim truth.** Evaluate the support for the material claim, not only the reputation of the source.
4. **Inference is not evidence.** Model inference may connect evidence, but it must never masquerade as sourced support.
5. **Conflicts stay visible.** Do not silently choose a winner when credible evidence materially disagrees.
6. **Verification depth should match consequence.** Spend effort on claims whose error would materially change understanding, action, or decisions.

## Derived insights

An insight may combine well-supported premises into a relationship that no
single source explicitly states. Inference remains inference even when every
premise is source-backed. The insight's `derived_from` links make its origin
inspectable; they do not constitute evidence that the linked pages stated the
derived relationship.

For a derived insight, keep two questions separate:

1. **Lifecycle:** Is the idea `candidate`, `provisional`, or `established` as a
   result of challenge, additional support, testing, or repeated useful use?
2. **Epistemic assessment:** How strong and contested are the material claims
   under this rigorous verification process?

The lifecycle is represented by the insight page's top-level `status`. The
existing nested `epistemic.status` is used for the material claim when a
rigorous assessment is warranted. Do not use an `established` lifecycle state
to imply that a source explicitly stated the relationship.

## What counts as a material claim

A material claim is one whose truth or falsity would meaningfully affect the durable page, a downstream conclusion, a project decision, or future retrieval.

Typical material claims include:

- quantitative results or comparisons;
- causal claims;
- claims of superiority, safety, reliability, or effectiveness;
- claims that overturn or narrow existing durable knowledge;
- claims that depend strongly on interpretation;
- time-sensitive facts likely to change;
- claims used to support consequential decisions.

Routine definitions, obvious paraphrases of authoritative documentation, and low-impact descriptive details usually do not need claim-level review unless they are disputed or central to the task.

## Evidence is claim-relative

Prefer the strongest evidence appropriate to the claim.

An official specification may be sufficient for what an API promises. Source code may be strongest for what a particular implementation currently does. An original paper may be primary evidence for what its experiment found, but not automatically sufficient for a broad claim that the method is generally superior.

There is no universal "two sources" rule. Independent corroboration is valuable when it actually reduces uncertainty; duplicative secondary sources do not become strong evidence merely by being numerous.

Never treat these as sufficient evidence by themselves:

- search-result snippets;
- titles or filenames;
- abstracts when the claim depends on details outside the abstract;
- tables of contents;
- AI-generated summaries;
- another wiki page that does not preserve its own provenance.

## Rigorous verification workflow

For each material claim:

```text
claim
  ↓
identify exact support
  ↓
inspect strongest appropriate primary/authoritative evidence
  ↓
look for meaningful corroboration or contradiction when needed
  ↓
separate evidence from interpretation
  ↓
assign epistemic status
  ↓
promote, keep provisional, investigate, or decline
```

### 1. State the claim precisely

Avoid verifying a broader statement than the evidence supports. Preserve scope, conditions, population, version, date, benchmark, and other qualifiers that materially affect meaning.

### 2. Locate explicit support

Record where the supporting source actually supports the claim. Do not fill a missing premise with model knowledge and then attribute the completed argument to the source.

### 3. Check authority appropriate to the claim

Ask what kind of source could actually settle or strongly inform this claim. Prefer primary or authoritative material when available.

### 4. Search for meaningful conflict

Actively check for contradiction when the claim is novel, consequential, surprising, disputed, or inconsistent with existing durable knowledge.

Do not perform ceremonial searches merely to satisfy a count.

### 5. Assess the claim

Use these statuses for `epistemic.status`:

- `established` — strong enough for normal durable use within the stated scope;
- `provisional` — useful but evidence is incomplete, indirect, narrow, or still uncertain;
- `contested` — credible evidence materially disagrees or interpretation remains unresolved.

`rejected` is a workflow outcome, not a wiki truth status. Unsupported or disproven candidate knowledge should normally not be promoted as a durable world claim; preserve it only where its historical or source context is useful.

Evidence strength may be recorded as `high`, `medium`, or `low`. It is a qualitative support label, not a probability of truth.

## Epistemic metadata

Do not burden every standard-mode page with epistemic fields.

In rigorous mode, add metadata for material knowledge when it improves future retrieval and review. A minimal page-level form is:

```yaml
epistemic:
  mode: rigorous
  status: established | provisional | contested
  evidence_strength: high | medium | low
  verified_at: YYYY-MM-DD
```

Use page-level status only when it honestly represents the important claims on the page. If a page contains claims with materially different support, annotate the relevant sections or claims instead of giving the entire page a misleading single status.

Supporting and conflicting source links should remain inspectable in the body or structured metadata.

## Progressive hardening

`standard` and `rigorous` do not create separate knowledge stores.

A page may begin as normal source-backed knowledge and later receive rigorous verification:

```text
standard knowledge
      ↓
rigorous re-check
      ↓
same canonical page
+ stronger provenance
+ explicit uncertainty
+ epistemic status where useful
```

Never fork `wiki/` into trusted and untrusted copies merely because verification depth changed.

## Automatic handling in rigorous mode

Human review is not required for every claim.

The agent may promote without review when support is clear, the source is appropriate and directly inspected, interpretation is minimal, no meaningful conflict is found, and the result does not overturn consequential existing knowledge.

When those conditions are not met, prefer `provisional`, `contested`, or investigation over forced certainty.

## Risk-based human review

Request human review when at least one of these is true:

- credible sources materially conflict;
- a change would overturn established durable knowledge;
- the conclusion depends heavily on model interpretation;
- evidence is weak but the claim may affect an important decision;
- the user explicitly requested approval before promotion;
- the cost of a false durable claim is unusually high.

Do not ask the human simply:

> Is this claim true?

Provide a compact review packet instead:

```text
Candidate claim:
...

Why it matters:
...

Supporting evidence:
...

Conflicting or missing evidence:
...

Agent assessment:
status: provisional | contested
evidence strength: low | medium | high

Proposed repository change:
...

Recommended handling:
...
```

Offer handling choices such as:

- **Approve** — accept the proposed durable handling;
- **Keep provisional** — retain the claim with visible uncertainty;
- **Investigate** — gather stronger or conflicting evidence before deciding;
- **Reject** — do not promote the candidate claim.

A non-expert reviewer should be able to choose among these without pretending to possess domain expertise.

## Investigation

If the reviewer chooses `Investigate`, the agent should seek the evidence most likely to change the assessment, not merely collect more links.

Prioritize:

1. missing primary or authoritative material;
2. direct evidence for the disputed premise;
3. independent replication or corroboration where relevant;
4. credible counterevidence;
5. newer evidence when freshness matters.

Return to review only when the evidence state materially changes or when further investigation reaches a clear limitation.

## Retrieval implications

Epistemic status must survive retrieval.

When answering from rigorous knowledge:

- do not phrase `provisional` knowledge as settled fact;
- surface `contested` status when it matters to the answer;
- prefer stronger, fresher, better-scoped evidence when claims conflict;
- do not hide uncertainty merely because a concise answer would be easier.

The purpose of epistemic metadata is not decoration. It exists so future agents can use durable knowledge at the strength the evidence actually supports.
