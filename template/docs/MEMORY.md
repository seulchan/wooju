# Personal Memory

Read this document before creating, updating, retrieving, or superseding durable personal memory.

`memory/` is a first-class layer for durable knowledge about the user. It is not general world knowledge, a transcript archive, or a duplicate of project files.

Use folders for **different lifecycles** and metadata for **different meanings**.

```text
memory/
├── records/      # durable personal knowledge
├── events/       # append-oriented history
└── state/        # current-state projections
```

- `records/` answers: **What durable things are known about the user?**
- `events/` answers: **What happened, and when?**
- `state/` answers: **What is true now?**

Do not create a new folder for every semantic type. Facts, preferences, goals, constraints, and durable decisions share a similar lifecycle and belong in `records/`, distinguished by metadata.

## `memory/records/` — durable personal records

Use `records/` for personal information likely to matter across future conversations or projects.

Recommended `type` values:

```text
fact
preference
goal
constraint
decision
relationship
routine
other
```

Start with the smallest useful vocabulary. Add a new controlled type only when real records repeatedly fail to fit the existing set.

Examples:

- technical background → `type: fact`;
- preferred explanation style → `type: preference`;
- returning to full-time work → `type: goal`;
- limited weekday focus time → `type: constraint`;
- adopting a durable personal workflow → `type: decision`.

Semantic units should be precise, but storage units should not become absurdly atomic. Prefer coherent profile pages such as `technical-profile.md`, `learning-preferences.md`, or `career-context.md` over one Markdown file per sentence.

A durable personal decision belongs here only when it remains meaningful beyond one project. Project-local architecture or implementation decisions stay under that project's `decisions/` directory. Promote a project decision into `memory/records/` only when it becomes a lasting personal convention or cross-project choice.

## `memory/events/` — append-oriented history

Use `events/` for meaningful occurrences whose historical ordering matters.

Examples include starting or completing a course, changing jobs, moving, selling or purchasing a major asset, reaching a project milestone, or changing an important routine or commitment.

Events record **what happened**. Do not silently rewrite an old event to make it match current state. Correct factual mistakes explicitly, but preserve genuine history.

Prefer chronological storage rather than one file per tiny event. Start simple:

```text
memory/events/
├── 2026.md
├── 2027.md
└── ...
```

Split by month or topic only when scale makes a yearly file unwieldy. Major events may receive their own page when they deserve an independent retrieval target.

## `memory/state/` — current-state projections

Use `state/` for mutable summaries that answer: **What is true now?**

Examples include current career status, current learning focus, current household context, active financial constraints, and current environment or tool setup.

Prefer domain-level state pages:

```text
memory/state/
├── career.md
├── learning.md
├── family.md
├── finance.md
└── environment.md
```

State is a projection, not the historical ledger. When a meaningful event or decision changes current state, update the relevant state page and link back to the supporting event or record when useful.

> **Events preserve history. State provides the latest projection.**

## Memory admission policy

Do not turn every conversational detail into durable memory. Store personal information only when it is likely to improve future assistance or preserve meaningful history.

A candidate should normally satisfy at least one of these:

- it is likely to materially change a future answer or recommendation;
- it will probably be needed repeatedly;
- it expresses a durable preference, goal, constraint, relationship, or routine;
- it records an important decision and its rationale;
- it is necessary to understand current state;
- it forms a meaningful part of personal or project history.

Usually do **not** promote one-off conversational details, transient moods, passing thoughts, a single stylistic request with no evidence of persistence, incidental tool use, casual facts unlikely to matter again, or speculative model interpretations of the user.

Optimize for signal, not memory volume.

## Personal-memory metadata

Use metadata to represent meaning, time, provenance, and supersession rather than encoding all semantics in directory names.

Recommended shape for a record:

```yaml
---
type: fact | preference | goal | constraint | decision | relationship | routine | other
subject: user
domains: []
observed_at: YYYY-MM-DD
valid_from: YYYY-MM-DD | YYYY | unknown
valid_until: YYYY-MM-DD | null
provenance: user_explicit | user_confirmed | observed | imported | inferred
status: current | historical | superseded
superseded_by:
---
```

Events may additionally use an intrinsic event date. State pages may omit a semantic `type` when the page itself is explicitly a current-state projection.

Interpretation:

- `observed_at` — when the information entered the system;
- `valid_from` — when it became true, if known;
- `valid_until` — when it stopped being true, if known;
- `provenance` — how the system knows it;
- `status` — whether the record should still influence current answers.

Do not invent dates merely to satisfy a schema. Omit or use `unknown` where appropriate.

## Inference rule

`inferred` memories require special caution.

Do not promote a behavioral pattern or model guess into a durable personal fact, preference, goal, or constraint merely because it seems plausible.

Prefer one of these:

1. keep the inference local to the current analysis;
2. record it explicitly as `inferred` with supporting evidence when durable tracking is genuinely useful;
3. wait for explicit user confirmation before promoting it to a stronger record.

Explicit user information outranks model inference.

## Supersession

When newer information changes an older personal record or state:

- update the canonical current page;
- preserve meaningful history;
- mark old records as `historical` or `superseded` when useful;
- link to the replacing record when practical;
- record why the answer changed.

Do not equate newer with better automatically. Supersession requires evidence or an explicit user decision.
