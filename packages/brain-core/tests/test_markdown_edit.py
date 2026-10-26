import pytest

from brain_core.markdown import set_frontmatter_value, split_frontmatter

NOTE = "---\ntitle: 테스트  # 메모\nreview_after: 2026-01-01\ntags: [a]\n---\n# 본문\n"


def test_replace_keeps_everything_else():
    out = set_frontmatter_value(NOTE, "review_after", "2027-01-27")
    assert out == NOTE.replace("2026-01-01", "2027-01-27")


def test_add_and_remove():
    added = set_frontmatter_value("---\ntitle: x\n---\nbody\n", "review_after", "2027-01-01")
    assert split_frontmatter(added)[0]["review_after"].isoformat() == "2027-01-01"
    removed = set_frontmatter_value(NOTE, "review_after", None)
    assert "review_after" not in removed and "tags: [a]" in removed


def test_no_frontmatter_and_unclosed():
    assert set_frontmatter_value("# x\n", "review_after", "2027-01-01").startswith(
        "---\nreview_after"
    )
    with pytest.raises(ValueError):
        set_frontmatter_value("---\ntitle: x\n", "review_after", "2027-01-01")
