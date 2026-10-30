# Roadmap

What Wooju is for, and what the next three releases contain. Settled design
decisions live in [DECISIONS.md](DECISIONS.md); this file is about direction
and order. Written after 0.5.0 (October 2026) from a research review of the
agent-memory landscape; the evidence is summarized at the end.

## What Wooju is

**Wooju is a knowledge base you read, review and own. AI agents (the local
model, Claude, others later) can read it and propose to it, but nothing is
written without you. That is why your agents can trust it as memory.**

The first sentence is the identity; the second is the consequence. Wooju is
not "a memory layer for AI agents". That phrase names a market split between
free memory bundled into ChatGPT, Claude and Gemini on one side and
venture-funded developer infrastructure (Mem0, Letta, Zep) on the other, and
a one-person Mac app does not win in between. What the labs structurally do
not offer is the ground Wooju stands on: plain files the person can read,
export and move; offline by default; a record of who wrote what, from which
source, and what replaced what; and a human in front of every write.

Three rules follow from this, and every item below is checked against them:

1. **The Brain outlives the app.** Markdown and git are the canonical store.
   Anything the app adds (indexes, vectors, progress files) is derived and
   disposable. The MCP server, the CLI and any export are thin adapters.
2. **Trust is a measurable design, not a slogan.** Provenance is attached by
   the server at proposal time, survives any rewriting by the model, is shown
   to the reviewer, and is enforced again when a note is used. "Trustworthy"
   means these four things hold, and the app measures whether they do.
3. **No hard parts for a non-developer.** Unchanged from DECISIONS.md, and it
   still wins conflicts. Installing Wooju must not need Terminal or System
   Settings.

## 0.6 — Source-visible review

The approval gate is Wooju's safety story and, today, its weakest link.
Anthropic's own data shows Claude Code users approve 93% of permission
prompts; a local 4B–9B model fabricates in roughly a quarter of document-QA
cases. A gate that is rubber-stamped launders model errors with a "user
approved" signature. 0.6 makes the gate worth having.

- **Origin on every proposal.** The server records where a proposal came from
  (a dropped file, a fetched link, Telegram, iCloud, Claude over MCP, the
  user's own typing) and carries it with `made_by`. The model may rewrite
  the content; it cannot change the origin.
- **Review cards show the source, not the paraphrase.** A card shows the
  original excerpt and the diff side by side. A summary alone is never the
  only thing a reviewer sees.
- **External content that gives instructions is always reviewed one by
  one.** A fetched page or dropped PDF containing imperative or "remember
  this" patterns escalates its proposal to individual review, whatever its
  risk tier. This is the memory-poisoning path measured in the literature.
- **Risk-tiered approval, measured.** Low risk (formatting, topic links) is
  automatic; medium risk goes to a weekly batch "audit"; high risk (rules,
  preferences, personal memory, facts from external sources) is approved at
  once, individually. The app logs approve/reject/edit rates locally, like
  `topics.json`. If the approve rate approaches 93%, the gate is not working
  and this roadmap is reopened.
- **Signed and notarized app.** An Apple Developer account removes the
  "Open Anyway" step, the one install step that breaks rule 3 today.

Not in 0.6: a temporal knowledge graph, a graph database, automatic fact
merging, background "dreaming" consolidation (the research name for
provenance laundering).

Gate: a new user installs without visiting System Settings; every review
card shows its origin and source excerpt; the approval log exists and is
shown in Settings.

Status (October 30, 2026): done except signing, which waits for the Apple
Developer account. Origin on every proposal, source-visible cards with
diffs, holding material that talks to an AI, risk tiers and the approval
log are in; details in DECISIONS.md, "Review that is worth having".

## 0.7 — The way out

"User-owned" is only true if the data can leave. No portability standard
exists yet (the Portable Agent Memory paper is a single-author proposal with
no verifiable implementation), and the only format the labs actually import
is a dated plain-text list pasted into a chat. So 0.7 ships the cheap, real
exits and nothing speculative.

- **Export.** Selected notes rendered as a `[date] – content` plain list,
  which is what Claude's and Gemini's memory import accept, with an optional
  token budget.
- **Import, with review.** Claude's memory export text, and Claude Code's
  `~/.claude/projects/*/memory/*.md`, land in the inbox and go through the
  same proposal and approval path as any other material. This is the one
  legitimate route for pulling a lab's memory into a Brain.
- **Adapters beyond MCP.** A `wooju` CLI and an Agent Skill file (how to
  read, search and propose), so an agent that prefers a shell or a skill
  over MCP can still use the Brain. The MCP 2.0 migration is done here, once.
- **"If the app dies, the Brain lives."** A one-page document showing the
  Brain opening in any editor and any git client, with nothing lost.

Not in 0.7: implementing PAM, `.af` or any proposed protocol; cryptographic
signing or capability tokens; a cloud sync service; coordinating concurrent
writes from several agents.

Gate: a Brain exported, imported into Claude and read back correctly; a
Brain opened in Obsidian and plain git with every note and its history
intact.

## 0.8 — Use-time enforcement and retrieval

Defense studies agree on one requirement: provenance bound at write time is
not enough; it must also be enforced when memory is used. And retrieval
quality moves answer accuracy by about 20 points where write strategy moves
it by 3–8. 0.8 spends on both.

- **Origin travels with every citation.** Ask, the Challenger and the MCP
  server pass a note's origin along with its text. A note that came from an
  external source can be cited as a fact but is never interpreted as an
  instruction; the separation is in code, not in a prompt.
- **Forgetting that works.** Retiring a note follows the "grounds changed"
  chain down to every note that rests on it, so a request to forget
  something removes what was derived from it too. Benchmarks show no current
  memory system passes more than 1.5% of such requests; a provenance graph is
  the only structure shown to make it possible.
- **Retrieval.** Hybrid search, section-level indexing, splitting long notes.
  This is the largest single lever on answer quality and the one most
  neglected so far.
- **First-run gate, re-run.** Ten to twenty non-developers, three minutes to
  a first saved note, with the signed app. One primary language per release.

Not in 0.8: competing with the labs on recall; immediate approval for every
write (the gate stays tiered); a second local-model family (a Korean-tuned
model stays an option, not a default).

Gate: the Ask eval includes poisoned-note cases and the answer never follows
an instruction found in a note; a forget request removes derived facts;
retrieval eval improves over 0.5.0 on the same questions.

## Standing decisions

- **The local model is not the point.** Trust comes from what enters the
  Brain and with what provenance, not from where inference runs. API keys
  are allowed (DECISIONS.md). Model revisions are pinned; summaries are
  labelled as drafts; facts from external sources are always shown with the
  original excerpt.
- **Reduce the stack where possible.** Tauri, a PyInstaller sidecar, an
  external Ollama and MCP are four upgrade cadences, plus an annual macOS
  release that breaks sidecar binaries and Gatekeeper rules. Each release
  asks whether one of these can go.
- **A second maintainer, early.** A trust layer that stops being maintained
  is not trusted. The Brain-outlives-the-app rule is the fallback; a second
  maintainer is the plan.

## When to revisit this

Any of these in the next six months reopens the direction, not just the
order:

- A lab or the MCP working group publishes a structured memory schema.
- The W3C memory-interoperability group gains chairs and participants from
  more than one organization.
- A Portable Agent Memory implementation appears with real users.
- The 0.6 approval log shows the gate is being rubber-stamped.

## Evidence behind this roadmap

Full notes and sources are in the research review that produced this file
(October 2026). The findings that shaped it:

- **Market.** All funded memory products are developer infrastructure; none
  publishes revenue or paying-customer numbers. Consumer memory is a free
  retention feature at OpenAI, Anthropic and Google. Demand evidence is for
  *switching* providers without starting over, not for *owning* memory.
- **Portability.** No standard has adoption. The labs' import tools accept a
  dated plain-text list; Markdown is the common denominator. Studies find
  externally organized, file-based memory ports across models better than
  graph triples (StructMemEval: interlinked Markdown 0.59 vs graph 0.22).
- **Competitors.** Markdown as agent memory is now common (Claude Code auto
  memory, OpenClaw, Basic Memory, Obsidian plugins with millions of
  downloads), but none combines human approval, per-entry provenance and
  plain files in a standalone app for non-developers.
- **Trust.** Memory poisoning is measured and large (MINJA 77–98%; 81.7%
  cross-session success against a Claude Code harness; detectors catch
  23–68%). Only platform-bound write-time provenance plus a use-time gate
  reached 0% in controlled studies; either half alone fails. No study has yet
  tested a *human* approval gate against these attacks.
- **Against.** Approval fatigue (93% approve rate), small-model fabrication
  (~25%), the unsigned-app install step, MCP's breaking 2.0 release, a small
  and developer-skewed segment, and the base rate of solo projects stalling.
  None of these gets better under a "memory layer" banner; all get worse.
