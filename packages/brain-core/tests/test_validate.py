"""Tests for the Brain validator. Every Brain is a temporary fixture."""

from __future__ import annotations

from brain_core.validate import main, validate_brain

SOURCE = """---
title: "Q3 2026 earnings release"
source_type: article
canonical_ref: "https://example.com/q3"
published: 2026-10-20
accessed: 2026-10-26
---
## One-line Summary

Revenue grew.
"""

CONCEPT = """---
title: Gross margin
---
# Gross margin

Revenue minus cost of goods sold, divided by revenue. See [[overviews/margins]].
"""

OVERVIEW = """---
title: Margins
---
# Margins

Links [[concepts/gross-margin]].
"""


def codes(report, severity=None):
    return sorted(i.code for i in report.issues if severity is None or i.severity == severity)


def test_clean_brain_passes(make_brain):
    brain = make_brain(
        {
            "sources/q3-earnings.md": SOURCE,
            "wiki/concepts/gross-margin.md": CONCEPT,
            "wiki/overviews/margins.md": OVERVIEW,
        }
    )
    report = validate_brain(brain)
    assert report.ok, report.issues
    assert report.files_checked == 3
    assert report.warnings == []


def test_root_files_and_docs_are_not_validated(make_brain):
    brain = make_brain({"AGENTS.md": "# TODO", "docs/X.md": "[[nowhere]]", "archive/old.md": "x"})
    report = validate_brain(brain)
    assert report.files_checked == 0 and report.issues == []


def test_source_requires_type_and_reference(make_brain):
    brain = make_brain({"sources/a.md": "---\ntitle: A\n---\nbody"})
    report = validate_brain(brain)
    messages = " ".join(i.message for i in report.errors)
    assert "source_type" in messages and "canonical_ref" in messages


def test_source_rejects_unknown_type_and_bad_date(make_brain):
    brain = make_brain(
        {"sources/a.md": "---\nsource_type: tweet\ncanonical_ref: x\naccessed: '2026-1-5'\n---\n"}
    )
    messages = " ".join(i.message for i in validate_brain(brain).errors)
    assert "source_type" in messages and "accessed" in messages


def test_impossible_yaml_date_is_reported(make_brain):
    brain = make_brain(
        {"sources/a.md": "---\nsource_type: book\ncanonical_ref: x\naccessed: 2026-13-01\n---\n"}
    )
    assert "impossible value" in " ".join(i.message for i in validate_brain(brain).errors)


def test_partial_published_dates_are_allowed(make_brain):
    for value in ("2024", "2024-05", "unknown", "2024-05-01"):
        brain = make_brain(
            {
                "sources/a.md": f"---\ntitle: A\nsource_type: book\ncanonical_ref: isbn\npublished: {value}\naccessed: 2026-10-26\n---\n"
            }
        )
        assert validate_brain(brain).ok, value


def test_invalid_yaml_is_an_error_not_silence(make_brain):
    brain = make_brain({"sources/a.md": "---\ntitle: [unclosed\n---\nbody"})
    assert "frontmatter" in codes(validate_brain(brain), "error")


def test_unclosed_frontmatter_is_an_error(make_brain):
    brain = make_brain({"wiki/concepts/a.md": "---\ntitle: A\nbody"})
    assert "frontmatter" in codes(validate_brain(brain), "error")


def _insight(status: str, challenge: bool, derived: str = '["[[concepts/gross-margin]]"]') -> str:
    body = "## Insight\n\nMargins lead re-ratings.\n"
    if challenge:
        body += "\n## Challenge\n\n- Counterexample: commodity cycles.\n"
    return (
        f"---\ntitle: Margin-led re-rating\norigin: synthesis\ninsight_kind: hypothesis\n"
        f"status: {status}\nderived_from: {derived}\n---\n{body}"
    )


def test_provisional_insight_requires_challenge(make_brain):
    brain = make_brain(
        {
            "wiki/concepts/gross-margin.md": CONCEPT,
            "wiki/overviews/margins.md": OVERVIEW,
            "wiki/questions/rerating.md": _insight("provisional", challenge=False),
        }
    )
    report = validate_brain(brain)
    assert "challenge" in codes(report, "error")


def test_candidate_without_challenge_is_only_a_warning(make_brain):
    brain = make_brain(
        {
            "wiki/concepts/gross-margin.md": CONCEPT,
            "wiki/overviews/margins.md": OVERVIEW,
            "wiki/questions/rerating.md": _insight("candidate", challenge=False),
        }
    )
    report = validate_brain(brain)
    assert report.ok
    assert "challenge" in codes(report, "warning")


def test_insight_needs_derivation_and_valid_kind(make_brain):
    brain = make_brain({"wiki/questions/x.md": _insight("candidate", True, derived="[]")})
    messages = " ".join(i.message for i in validate_brain(brain).errors)
    assert "derived_from" in messages


def test_insight_in_project_is_checked_too(make_brain):
    brain = make_brain(
        {
            "projects/p/idea.md": "---\norigin: synthesis\ninsight_kind: guess\nstatus: candidate\nderived_from: [x]\n---\n"
        }
    )
    messages = " ".join(i.message for i in validate_brain(brain).errors)
    assert "insight_kind" in messages and "derived_from entry 'x'" in messages


def test_broken_wikilink_and_markdown_link(make_brain):
    brain = make_brain(
        {
            "wiki/concepts/a.md": "# A\n\n[[missing-page]] and [b](../overviews/b.md) and [web](https://x.y)"
        }
    )
    errors = [i for i in validate_brain(brain).errors if i.code == "broken-link"]
    assert len(errors) == 2


def test_links_inside_code_fences_are_ignored(make_brain):
    brain = make_brain(
        {
            "wiki/concepts/a.md": "# A\n\n```\n[b](nope.md)\n```\n",
            "wiki/overviews/o.md": "[[concepts/a]]",
        }
    )
    assert validate_brain(brain).ok


def test_durable_page_must_not_link_to_inbox(make_brain):
    brain = make_brain(
        {"inbox/clip.md": "raw", "wiki/concepts/a.md": "# A\n\nFrom [clip](../../inbox/clip.md)"}
    )
    assert "inbox-link" in codes(validate_brain(brain), "error")


def test_wiki_pages_must_use_known_sections(make_brain):
    brain = make_brain({"wiki/loose.md": "# Loose", "wiki/notes/x.md": "# X"})
    errors = [i for i in validate_brain(brain).errors if i.code == "location"]
    assert len(errors) == 2


def test_secrets_are_errors_everywhere_including_inbox(make_brain):
    brain = make_brain(
        {
            "inbox/keys.md": "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "memory/records/bank.md": "---\ntype: fact\nprovenance: user_explicit\n---\ncard 4111 1111 1111 1111",
        }
    )
    sensitive = [i for i in validate_brain(brain).errors if i.code == "sensitive"]
    assert {i.path for i in sensitive} == {"inbox/keys.md", "memory/records/bank.md"}


def test_ordinary_numbers_are_not_card_numbers(make_brain):
    brain = make_brain({"wiki/concepts/a.md": "# A\n\nRevenue 1234567890123 KRW; [[concepts/a]]"})
    assert not [i for i in validate_brain(brain).issues if i.code == "sensitive"]


def test_memory_record_schema_and_supersession(make_brain):
    brain = make_brain(
        {
            "memory/records/style.md": "---\ntype: preference\nprovenance: user_explicit\nstatus: current\nsuperseded_by: other\n---\n",
            "memory/records/bad.md": "---\ntype: mood\nprovenance: guessed\n---\n",
        }
    )
    report = validate_brain(brain)
    assert "supersession" in codes(report, "error")
    bad = " ".join(i.message for i in report.errors if i.path == "memory/records/bad.md")
    assert "type" in bad and "provenance" in bad


def test_inferred_memory_is_flagged(make_brain):
    brain = make_brain(
        {
            "memory/records/x.md": "---\ntype: preference\nprovenance: inferred\nobserved_at: 2026-10-26\n---\n"
        }
    )
    assert "inferred-memory" in codes(validate_brain(brain), "warning")


def test_warnings_orphan_duplicate_naming_placeholder_empty_section(make_brain):
    brain = make_brain(
        {
            "wiki/concepts/Gross_Margin.md": "---\ntitle: Gross margin\n---\n## Why\n\nTODO\n\n## Example\n",
            "wiki/concepts/gross-margin.md": CONCEPT,
            "wiki/overviews/margins.md": OVERVIEW,
        }
    )
    report = validate_brain(brain)
    warned = set(codes(report, "warning"))
    assert {"orphan", "duplicate-title", "naming", "placeholder", "empty-section"} <= warned
    assert report.ok


def test_rigorous_mode_asks_for_epistemic_block(make_brain):
    brain = make_brain(
        {
            "wooju-brain.yaml": "knowledge:\n  quality_mode: rigorous\n",
            "wiki/concepts/gross-margin.md": CONCEPT,
            "wiki/overviews/margins.md": OVERVIEW,
        }
    )
    assert "epistemic" in codes(validate_brain(brain), "warning")


def test_validator_never_writes(make_brain):
    brain = make_brain({"wiki/concepts/a.md": "# A\n\n[[missing]]"})
    before = {p: p.read_bytes() for p in brain.rglob("*") if p.is_file()}
    validate_brain(brain)
    after = {p: p.read_bytes() for p in brain.rglob("*") if p.is_file()}
    assert before == after


def test_cli_exit_codes(make_brain, capsys):
    good = make_brain(
        {"wiki/concepts/gross-margin.md": CONCEPT, "wiki/overviews/margins.md": OVERVIEW}
    )
    bad = make_brain({"sources/a.md": "---\ntitle: A\n---\n"})
    assert main([str(good)]) == 0
    assert main([str(bad), "--json"]) == 1
    assert '"errors": 2' in capsys.readouterr().out


def test_missing_root(tmp_path):
    report = validate_brain(tmp_path / "nope")
    assert not report.ok
