from brain_core.index import BrainIndex
from brain_core.markdown import split_frontmatter
from brain_core.topics import add_members, is_topic, read_state, remove_member

TOPIC = """---
title: 한국은행 기준금리
---
# 한국은행 기준금리

사용자가 쓴 요약. [FocusEconomics](../../sources/focus.md)

## 관련

- [[concepts/korea-discount]]
"""


def _records(tmp_path, files):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    index = BrainIndex()
    index.scan(tmp_path)
    return index


def note(title):
    return f"---\ntitle: {title}\nsource_type: article\ncanonical_ref: x\n---\n# {title}\n\n본문\n"


def test_members_are_added_in_their_own_section_and_the_body_is_untouched(tmp_path):
    index = _records(
        tmp_path,
        {
            "wiki/overviews/bok.md": TOPIC,
            "sources/focus.md": note("FocusEconomics"),
            "sources/fnnews.md": note("파이낸셜뉴스"),
            "wiki/concepts/korea-discount.md": "---\ntitle: 코리아 디스카운트\n---\n# 코리아 디스카운트\n",
        },
    )
    assert is_topic(index.get("wiki/overviews/bok"))
    members = [
        index.get(i) for i in ("sources/focus", "sources/fnnews", "wiki/concepts/korea-discount")
    ]
    text, added = add_members(TOPIC, "wiki/overviews/bok.md", members, "ko")
    # Already linked by the user (Markdown link or wikilink): not repeated.
    assert added == ["sources/fnnews.md"]
    assert TOPIC.split("---\n# ")[1].split("## 관련")[0] in text  # the user's body is unchanged
    assert "사용자가 쓴 요약. [FocusEconomics](../../sources/focus.md)" in text
    assert text.rstrip().endswith("## 이 주제의 노트\n\n- [파이낸셜뉴스](../../sources/fnnews.md)")
    assert split_frontmatter(text)[0]["topic_notes"] == ["sources/fnnews.md"]

    # Adding again changes nothing.
    again, added = add_members(text, "wiki/overviews/bok.md", members, "ko")
    assert added == [] and again == text


def test_a_note_the_user_removed_is_never_put_back(tmp_path):
    index = _records(
        tmp_path,
        {"wiki/overviews/bok.md": TOPIC, "sources/a.md": note("A"), "sources/b.md": note("B")},
    )
    a, b = index.get("sources/a"), index.get("sources/b")
    text, _ = add_members(TOPIC, "wiki/overviews/bok.md", [a, b], "en")
    assert "## Notes on this topic" in text
    # The user deletes the line for A in the editor.
    edited = text.replace("- [A](../../sources/a.md)\n", "")
    text2, added = add_members(edited, "wiki/overviews/bok.md", [a, b], "en")
    assert added == []
    state = read_state(text2, "wiki/overviews/bok.md")
    assert state.excluded == ["sources/a.md"] and state.added == ["sources/b.md"]
    assert "sources/a.md" not in state.in_section

    # Taking B out with the button works the same way.
    text3 = remove_member(text2, "wiki/overviews/bok.md", "sources/b.md")
    state = read_state(text3, "wiki/overviews/bok.md")
    assert state.in_section == [] and state.excluded == ["sources/a.md", "sources/b.md"]
    assert add_members(text3, "wiki/overviews/bok.md", [a, b], "en")[1] == []


def test_a_note_joins_its_closest_topics_only():
    from brain_core.topics import match_topics

    topics = {"rates": [1.0, 0.0, 0.0], "valueup": [0.0, 1.0, 0.0], "tax": [0.7071, 0.7071, 0.0]}
    assert [t for _, t in match_topics([0.98, 0.2, 0.0], topics)] == ["rates"]
    # Close to two topics equally: both, never more than two.
    both = match_topics(
        [0.6, 0.6, 0.53], {"a": [0.6, 0.6, 0.53], "b": [0.6, 0.6, 0.53], "c": [0.6, 0.6, 0.53]}
    )
    assert len(both) == 2
    assert match_topics([0.0, 0.0, 1.0], topics) == []  # nothing close enough


def test_emerging_groups_need_enough_close_notes():
    from brain_core.topics import emerging

    v = {
        "a": [1.0, 0.0],
        "b": [0.99, 0.14],
        "c": [0.98, 0.2],
        "d": [0.97, 0.24],
        "x": [0.0, 1.0],
        "y": [0.1, 0.99],
    }
    assert emerging(v, exclude=set()) == [["a", "b", "c", "d"]]
    assert emerging(v, exclude={"a"}) == []  # three left: too few for a topic
