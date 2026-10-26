# Repository Operations

Read this document before changing schemas, naming, links, validators, logs, generated indexes, or repository mechanics.

## Canonical repository layout

```text
personal-kb/
├── AGENTS.md
├── CLAUDE.md -> AGENTS.md
├── docs/
│   ├── KNOWLEDGE.md
│   ├── MEMORY.md
│   ├── WORK.md
│   ├── INGEST.md
│   ├── RETRIEVAL.md
│   └── OPERATIONS.md
├── index.md
├── indexes/
├── inbox/
├── library/
├── sources/
├── wiki/
│   ├── concepts/
│   ├── overviews/
│   ├── questions/
│   ├── how-tos/
│   └── mental-models/
├── memory/
│   ├── records/
│   ├── events/
│   └── state/
├── projects/
├── areas/
├── logs/
├── scripts/
└── archive/
```

Do not create folders merely because a category might exist. Add structure when real content requires it.

## Naming and identity

Prefer stable, descriptive, kebab-case filenames.

Examples:

```text
wiki/concepts/gradient-accumulation.md
wiki/overviews/agent-memory.md
memory/records/learning-preferences.md
memory/state/career.md
projects/wooju-brain/architecture.md
```

Use dates in filenames only when the date is intrinsic to the record, such as an event, snapshot, or daily log.

Do not bulk rename mature pages without updating inbound links and generated indexes.

## Validation

Validators should check, where applicable:

- valid frontmatter;
- duplicate or near-duplicate durable pages;
- broken links;
- missing canonical source references;
- important orphaned pages;
- invalid paths;
- empty required sections;
- placeholder prose;
- stale generated indexes;
- conflicting controlled-vocabulary tags;
- derived insight metadata with an allowed `insight_kind` and lifecycle `status`, non-empty `derived_from`, and a `## Challenge` section;
- personal state marked current after a known superseding record;
- superseded records without a replacement link when one exists;
- project or area links pointing to archived material without explanation.

Validation can detect structural problems, not semantic truth.

When a validator exposes an incomplete page, fix the underlying knowledge problem rather than deleting the offending line merely to make the validator green.

## Logs

Logs are a concise narrative record of meaningful repository changes and rationale.

Suggested headings:

```text
## ingest | {topic} | {source or batch}
## synthesis | {topic} | {page}
## memory | {topic} | {record}
## supersede | {topic} | {claim or state}
## decision | {topic} | {decision}
## maintenance | {topic} | {task}
## query-to-knowledge | {topic} | {result page}
```

Log meaningful changes, why a durable claim or state changed, significant failed attempts, migrations, reclassification, and unresolved gaps.

Do not turn logs into a duplicate copy of the wiki or personal memory.

## Wikilinks and Obsidian

The Obsidian vault root is `wiki/` if Obsidian is used only for the durable knowledge layer.

Inside wiki pages, use vault-root-relative links:

```text
[[concepts/some-concept]]
[[overviews/some-overview]]
```

Do not prefix those links with `wiki/` when the vault root is already `wiki/`.

If Obsidian is later used across the entire repository, migrate link conventions intentionally rather than mixing two incompatible assumptions.

Links from `memory/`, `projects/`, `areas/`, or `sources/` may use normal Markdown links when cross-root wikilinks are ambiguous. Choose one convention and validate it consistently.

## Housekeeping

- No temporary extraction dumps or tool caches in durable folders.
- Put disposable artifacts in a system temp directory or ignored workspace.
- Never store secrets in Markdown frontmatter or logs.
- Do not create duplicate files just to satisfy a schema.
- Archive retired material rather than leaving ambiguous obsolete pages in active retrieval paths.
- Prefer reversible migrations for large reorganizations.
- If using git, make intentional commits that explain structural or semantic changes.

## Generated indexes

Generated indexes are navigation aids, not sources of truth.

Rebuild them when required by the task or after structural changes. Do not hand-edit generated content unless the generator itself is being changed.

Keep live search indexes, caches, locks, and model artifacts machine-local unless the repository intentionally versions them.
