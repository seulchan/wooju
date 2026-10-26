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

- **UI indexes the Brain's own manuals.** `docs/*.md`, `AGENTS.md`, `README.md`
  and `index.md` appear as 11 "other" records, and the example wikilinks inside
  `docs/` show up as unresolved references. The UI index should skip what the
  validator skips (only content layers, plus inbox).
- **Ingest needs today's date.** `accessed` and `observed_at` were filled by
  hand; the agent must stamp them, never the model.

## Not yet measured

- Local model quality (Qwen 3.5 4B/9B): run `evals/local_model_quality.py`
  against this dev Brain on an Apple Silicon Mac with Ollama.
