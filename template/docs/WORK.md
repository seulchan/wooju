# Projects and Areas

Read this document before changing project state, project decisions, or ongoing life-area context.

## `projects/` — finite goal-oriented work

A project has an intended outcome and eventually ends, pauses, or is abandoned.

Examples include building `wooju-brain`, completing a degree assignment, publishing a course, or preparing for a job interview.

Typical project contents:

```text
projects/{project}/
├── README.md
├── plan.md
├── status.md
├── decisions/
├── experiments/
└── notes/
```

Project files may contain local state and project-specific decisions.

Generalizable knowledge discovered during a project should be promoted into `wiki/` rather than duplicated permanently inside the project.

A project-local decision belongs in `projects/{project}/decisions/`. Promote it into `memory/records/` only when it becomes a lasting personal convention or cross-project choice.

## `areas/` — ongoing management context

An area is a continuing responsibility or life domain without a natural end date.

Examples include family, career, finance, health, learning, and household.

`areas/` should act primarily as a context hub or dashboard, not as the canonical store for personal facts.

An area page may link to:

- relevant current state in `memory/state/`;
- related typed records in `memory/records/`;
- relevant world knowledge in `wiki/`;
- active projects;
- recurring routines or review checklists.

This keeps management context separate from the underlying memory and knowledge records.

## Canonical-location rule

Avoid duplicating the same fact or explanation across `projects/`, `areas/`, `memory/`, and `wiki/`.

- general explanation → `wiki/`;
- durable fact about the user → `memory/`;
- project-specific status or decision → project;
- ongoing management dashboard → area.

Link from contexts to canonical records.

## Status and archive

When a project ends, pauses for the long term, or is abandoned, update its status explicitly and archive it when appropriate.

Do not leave dead project state mixed into active retrieval paths without a status marker.

Areas normally remain active, but their linked state may change. Update the canonical memory state rather than rewriting history inside the area page.
