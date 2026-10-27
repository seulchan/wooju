"""Unit tests for the pure Markdown parsing functions in brain_core.markdown."""

from brain_core.markdown import (
    extract_title,
    extract_wikilinks,
    make_snippet,
    normalize_target,
    split_frontmatter,
)


def test_split_no_frontmatter():
    fm, body = split_frontmatter("Just body\n# H1")
    assert fm == {}
    assert body == "Just body\n# H1"


def test_split_with_frontmatter():
    fm, body = split_frontmatter("---\ntitle: Hi\ntags: [a, b]\n---\nBody here")
    assert fm == {"title": "Hi", "tags": ["a", "b"]}
    assert body == "Body here"


def test_split_empty_frontmatter_block():
    fm, body = split_frontmatter("---\n---\nBody")
    assert fm == {}
    assert body == "Body"


def test_split_malformed_yaml_degrades_to_empty():
    # Unterminated flow sequence -> YAMLError -> empty frontmatter, body intact.
    fm, body = split_frontmatter("---\nlist: [a, b\n---\nBody")
    assert fm == {}
    assert body == "Body"


def test_split_non_mapping_frontmatter_degrades_to_empty():
    fm, body = split_frontmatter("---\njustastring\n---\nBody")
    assert fm == {}


def test_split_strips_bom_and_normalizes_crlf():
    fm, body = split_frontmatter("﻿---\r\ntitle: X\r\n---\r\nBody\r\nline2")
    assert fm == {"title": "X"}
    assert body == "Body\nline2"


def test_title_prefers_frontmatter_then_h1_then_filename():
    assert extract_title({"title": "FM"}, "# H1", "file.md") == "FM"
    assert extract_title({}, "# A Heading", "file.md") == "A Heading"
    assert extract_title({}, "no heading here", "my-note.md") == "my-note"


def test_title_skips_date_banner_h1_uses_following_h2():
    """A daily-log note whose only H1 is a bare date banner: the date is not the
    title; the entry's first content H2 is. Regression for ``logs/`` notes that
    previously surfaced a date-only title (e.g. "2026-08-08")."""
    body = "# 2026-08-08\n\n## ingest | LLM agent research papers | inbox batch\n\n- detail\n"
    assert extract_title({}, body, "2026-08-08-ingest.md") == (
        "ingest | LLM agent research papers | inbox batch"
    )


def test_title_date_banner_without_h2_falls_back_to_filename():
    """A date-banner H1 with no usable H2 degrades to the filename stem, never to
    the bare date."""
    assert extract_title({}, "# 2026-08-08\n\njust prose, no heading", "2026-08-08-thing.md") == (
        "2026-08-08-thing"
    )


def test_title_uses_a_non_date_h1_after_a_date_banner():
    """A date banner followed by a real H1 uses the real H1."""
    body = "# 2026-08-08\n\n# Real Title\n\nbody"
    assert extract_title({}, body, "note.md") == "Real Title"


def test_title_normal_h1_is_unchanged_by_date_logic():
    """A heading that merely contains digits/dashes (not a bare date) is a title."""
    assert extract_title({}, "# GPT-4 vs GPT-3.5", "note.md") == "GPT-4 vs GPT-3.5"


def test_title_skips_date_only_frontmatter_title_for_daily_log():
    """A parsed date metadata value must not hide the meaningful log entry title."""
    body = "# 2026-08-08\n\n## Review retrieval notes\n\nDetails."
    assert extract_title({"title": "2026-08-08"}, body, "2026-08-08.md") == (
        "Review retrieval notes"
    )


def test_wikilink_forms_and_embed_skip():
    body = (
        "[[llm-agent-memory]] "
        "[[concepts/llm-agent-memory]] "
        "[[llm-agent-memory|Agent Memory]] "
        "[[note#Section]] "
        "[[note^block]] "
        "![[image.png]]"
    )
    links = [(wl["target"], wl["label"], wl["anchor"]) for wl in extract_wikilinks(body)]
    assert ("llm-agent-memory", None, None) in links
    assert ("concepts/llm-agent-memory", None, None) in links
    assert ("llm-agent-memory", "Agent Memory", None) in links
    assert ("note", None, "Section") in links
    assert ("note", None, "block") in links
    # Embed (image) is ignored.
    assert all(target != "image.png" for target, _, _ in links)
    assert len(links) == 5


def test_snippet_basic_and_empty():
    content = "alpha " * 60
    snippet = make_snippet(content, ["alpha"])
    assert "alpha" in snippet
    assert make_snippet("", ["x"]) == ""


# ---------------------------------------------------------- normalize_target


def test_normalize_target_wikilink_forms():
    assert normalize_target("[[overviews/foo]]") == "overviews/foo"
    assert normalize_target("[[concepts/foo|Label]]") == "concepts/foo"
    assert normalize_target("[[foo#Section]]") == "foo"
    assert normalize_target("[[foo^block]]") == "foo"


def test_normalize_target_markdown_link_form():
    # Relative path from a nested note, with .md suffix and ../ traversal.
    assert normalize_target("[Label](../../sources/foo.md)") == "sources/foo"
    assert normalize_target("[X](./wiki/foo.md)") == "wiki/foo"
    assert normalize_target("[X](foo.md)") == "foo"


def test_normalize_target_bare_and_empty():
    assert normalize_target("wiki/concepts/foo") == "wiki/concepts/foo"
    assert normalize_target("foo.md") == "foo"
    assert normalize_target("") is None
    assert normalize_target("   ") is None
    assert normalize_target(None) is None  # type: ignore[arg-type]
    assert normalize_target("[[  ]]") is None  # blank inner target


def test_markdown_links_to_notes_count_as_links():
    from brain_core.markdown import extract_note_links

    body = (
        "See [the spacing effect](../concepts/spacing-effect.md#example), "
        "[a source](../../sources/forgetting-curve.md), ![img](pic.md), "
        "[web](https://example.com/x.md), [file](../../library/a.txt), "
        "[outside](../../../elsewhere.md).\n\n```\n[code](../concepts/nope.md)\n```\n"
    )
    links = extract_note_links(body, "wiki/how-tos/review.md")
    assert [(x["target"], x["anchor"], x["kind"]) for x in links] == [
        ("wiki/concepts/spacing-effect", "example", "markdown"),
        ("sources/forgetting-curve", None, "markdown"),
    ]
    assert links[0]["label"] == "the spacing effect"
