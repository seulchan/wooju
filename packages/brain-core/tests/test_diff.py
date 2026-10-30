from brain_core.diff import body_diff

OLD = "---\ntitle: X\nmade_by: []\n---\n# X\n\nOne.\nTwo.\nThree.\nFour.\nFive.\nSix.\n"


def test_only_changed_lines_with_context_and_frontmatter_ignored():
    new = OLD.replace("made_by: []", 'made_by: [{"agent": "x"}]').replace("Four.", "Four, fixed.")
    d = body_diff(OLD, new, context=1)
    assert d == [
        {"kind": "same", "text": "Three."},
        {"kind": "remove", "text": "Four."},
        {"kind": "add", "text": "Four, fixed."},
        {"kind": "same", "text": "Five."},
    ]


def test_equal_bodies_have_no_diff_and_far_apart_changes_get_a_gap():
    assert body_diff(OLD, OLD) == []
    new = OLD.replace("One.", "1.").replace("Six.", "6.")
    kinds = [x["kind"] for x in body_diff(OLD, new, context=0)]
    assert kinds == ["remove", "add", "gap", "remove", "add"]


def test_long_diffs_are_cut():
    new = OLD + "\n".join(f"line {i}" for i in range(500))
    d = body_diff(OLD, new, limit=50)
    assert len(d) == 51 and d[-1]["kind"] == "gap"
