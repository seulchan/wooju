# Phase 1 findings

What writing 29 real notes (Korea value-up and re-rating research, in Korean)
taught us about the Brain rules, the schemas, and the tools. Each item says what
happened, what we did, and what should change. Dev Brain: `~/Projects/wooju-brain-dev`
(outside this repository).

Result: 29 notes (13 sources, 11 wiki pages, 2 insights, 1 memory record,
1 area, 1 project), **0 validator errors, 0 warnings** after fixing one
validator bug.

## Ambiguous classifications

| # | Case | What we chose | Why it was unclear | Proposed rule |
| --- | --- | --- | --- | --- |
| 1 | A general investing heuristic ("re-rating needs a discount and a catalyst") that no note in the Brain sources | `wiki/mental-models/`, not an insight | It is not derived from Brain notes (so not `origin: synthesis`), but it is also unsourced. The docs have no way to mark "background knowledge from the agent". | Add optional `origin: background` for unsourced general knowledge; retrieval shows it with lower weight. |
| 2 | A fast-changing macro series (Bank of Korea rate decisions) | `wiki/overviews/` with `review_after` | Overviews are meant to be broad maps, not trackers. Memory/state is for the user, not the world. | Allow a "tracker" page shape in overviews: dated table + `review_after`. |
| 3 | A provisional `tension` insight | `wiki/questions/` | SYNTHESIS.md routes "unresolved evidence-seeking" ideas to questions, but a tension is a finding, not a question. | Route `tension` and `pattern` insights to `concepts/` or `overviews/`; keep `questions/` for `hypothesis`. |
| 4 | Government press release (FSC) | `source_type: docs` | No type for official announcements or reports. | Consider adding `report` (government, think tank, company IR). Defer until more cases. |
| 5 | Evidence tier of an AI-assisted blog | Stated only in the body ("근거 수준이 낮다") | KNOWLEDGE.md defines four evidence tiers but no field for them. | Add optional `evidence_tier: 1-4` to sources so retrieval can rank them. |
| 6 | A number the source did not show (BoK August rate, text truncated) | Kept out of the summary; inference stated under limitations | Source notes must record only what the source states; the validator cannot check this. | Ingest agent prompt must forbid filling gaps; Challenger can flag "inferred" phrasing. |
| 7 | User profile fact that came from another Claude surface's memory | `provenance: user_explicit` | The user did state it, but in another product; `imported` also fits. | Rule: statement by the user anywhere → `user_explicit`; bulk import from another system → `imported`. |
| 8 | Linking a wiki page to a project folder | Markdown link to `projects/<p>/README.md` | `[[projects/<p>]]` does not resolve because the record id ends in `/README`. | Resolve a folder link to its `README` or `index` note. |

## Tool bugs found and fixed

- **Validator false positive:** an 18-digit news article ID inside a source URL
  passed the Luhn check and was reported as a card number. Number-shaped secret
  checks now ignore URLs. Regression test added.

## Tool issues to fix in phase 2

- **UI search includes the Brain's own manuals.** `docs/*.md`, `AGENTS.md`,
  `README.md` and `index.md` are indexed as `other`. This is intentional in the
  original UI (meta content), and the Attention view already ignores example
  links inside `docs/`. *Correction:* an earlier draft of this note said those
  links surfaced as unresolved references; they do not. Remaining issue: they can
  appear in search results. Low priority.
- **Ingest needs today's date.** `accessed` and `observed_at` were filled by
  hand; the agent must stamp them, never the model.

## Not yet measured

- Local model quality (Qwen 3.5 4B/9B): run `evals/local_model_quality.py`
  against this dev Brain on an Apple Silicon Mac with Ollama.

## Local model quality (measured 2026-10-26)

Run on the user's Apple Silicon Mac with Ollama against the 29-note dev Brain.
Output was constrained by JSON schema, temperature 0, thinking off. Inputs had
frontmatter removed, so the model saw only the note body.

| Model | Classify (all) | Classify sources | Classify others | Wrongly sent to memory | Source FM valid | source_type match | Summary ≤ 80 chars | Summary in Korean | Median tok/s | Time per note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| qwen3.5:4b | 69.0% | 61.5% | 75.0% | 7 | 100% | 84.6% | 62.1% | 100% | 15.2 | ~14 s |
| qwen3.5:9b | 75.9% | 92.3% | 62.5% | 3 | 100% | 92.3% | 100% | 100% | 8.4 | ~35 s |

What this means:

- **Neither model is safe for unreviewed filing.** Even 9B misfiles one note in
  four. Approval cards stay mandatory, and personal memory must never be chosen
  by the model alone.
- **4B mistakes external sources for personal memory** (7 notes sent to
  `memory/`). This is the most harmful error class. Ingest must decide
  "external source vs about the user" deterministically from where the item
  came from (dropped file or URL → source), and only ask the model to refine
  within that branch.
- **Most 9B errors land on the ambiguous cases above** (#2 tracker overview →
  memory, #3 insights → concepts/mental-models, area ↔ memory/state). Tightening
  those rules should help both models.
- **Schema-constrained output works.** Source frontmatter was 100% valid for both
  models. `source_type` misses were the government press release (#4, no
  fitting type) and one article labelled `experience`.
- **Korean spacing artifact.** Both models write "2026 년 7 월" instead of
  "2026년 7월" (4B in 26/29 summaries, 9B in 18/29). Fix deterministically after
  generation instead of prompting.
- **4B ignores length limits** (62% within 80 characters vs 100% for 9B).
- **Speed is acceptable for background ingest.** About 14 s per note on 4B and
  35 s on 9B for three tasks; first model load about 4–5 s.
- **Eval fix:** the first run scored `published` at 0% because the date is only in
  frontmatter, which the model never saw. It is now scored only when the body
  states the date.

Decision: keep the hardware mapping (8 GB → 4B, 16 GB+ → 9B). Phase 2 ingest
uses origin-based routing, rule fixes for cases #2–#4, and the spacing
normalizer, then re-runs this eval.

## Ask quality (2026-10-27, dev Brain, 20 questions, M1 16 GB)

`evals/ask_quality.py` with `evals/ask_questions.json` (12 Korean, 8 English).

| Search | hit@8 | MRR | Korean MRR | English MRR |
|---|---|---|---|---|
| Keyword (BM25) | 95% | 0.69 | 0.90 | 0.38 |
| Keyword + meaning (qwen3-embedding:0.6b) | 100% | 0.79 | 0.92 | 0.60 |

Answers with qwen3.5:9b: cites an expected note 90%, cites anything 95%,
answers in the question's language 100%, median 39 s per answer (16–67 s).
One answer cited nothing (BOK rate-hike reason); one cited a related but
unexpected note. Speed, not accuracy, is now the weakest part of Ask.

Fewer, shorter passages (6 × 700 chars instead of 8 × 1500): median answer
time 39 s → 30 s; cites an expected note 90% → 85% (the one change is a
question answered from knowledge notes that summarize the expected source).

Link-list sections ("관련 지식", "Related") rank at 0.3× so they stop taking
answer slots: for "한국은행이 기준금리를 올린 이유는?" the section that holds
the reason now makes the top 6. Keyword-only English hit@8 falls 88% → 62%
(MRR 0.38 → 0.50) because some English questions matched only link titles
and slugs; to be checked with meaning search and answers on the Mac.
