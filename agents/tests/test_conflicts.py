from pathlib import Path

from brain_core.index import BrainIndex
from brain_core.retrieve import Retriever
from wooju_agents.conflicts import add_section, find_conflicts, first_conflict, render_section
from wooju_agents.llm import LLMResult


class Fake:
    name, model = "fake", "fake"

    def __init__(self, data):
        self.data, self.calls = data, []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user))
        return LLMResult(self.data, "", 0, self.name, self.model)


def _passages(tmp_path: Path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "old.md").write_text(
        "---\ntitle: 자사주 소각 해설\nsource_type: article\ncanonical_ref: x\npublished: 2026-03-01\n---\n"
        "# 자사주 소각 해설\n\n## 핵심 내용\n\n- 자사주는 1년 안에 소각해야 한다.\n",
        encoding="utf-8",
    )
    index = BrainIndex()
    index.scan(tmp_path)
    return [p for _, p in Retriever(index).search("자사주 소각 기한")]


def test_conflicts_must_point_at_a_shown_passage(tmp_path):
    passages = _passages(tmp_path)
    provider = Fake(
        {
            "conflicts": [
                {"new_claim": "18개월 안에 소각", "existing": 1, "existing_claim": "1년 안에 소각"},
                {"new_claim": "x", "existing": 9, "existing_claim": "y"},
            ]
        }
    )
    found = find_conflicts(
        "# 새 자료\n\n- 18개월 안에 소각한다.", passages, provider, language="ko"
    )
    assert [(c.new_claim, c.passage.id) for c in found] == [("18개월 안에 소각", "sources/old")]
    assert "different time periods" in provider.calls[0][0]
    assert "(2026-03-01)" in provider.calls[0][1]


def test_section_links_the_other_note_and_sits_before_original(tmp_path):
    passages = _passages(tmp_path)
    provider = Fake(
        {"conflicts": [{"new_claim": "18개월", "existing": 1, "existing_claim": "1년"}]}
    )
    found = find_conflicts("x", passages, provider, language="ko")
    section = render_section(found, note_path="sources/new.md", language="ko")
    assert "[자사주 소각 해설](old.md)" in section
    note = "# 새 자료\n\n## 핵심 내용\n\n- 18개월\n\n## 원본\n\n- [원본 파일](../library/x.pdf)\n"
    out = add_section(note, section)
    assert out.index("## Conflicts") < out.index("## 원본")
    assert first_conflict(out) == "이 자료: 18개월 / 다른 노트 (자사주 소각 해설): 1년"


def test_no_passages_no_call():
    provider = Fake({"conflicts": []})
    assert find_conflicts("x", [], provider, language="en") == []
    assert provider.calls == []
