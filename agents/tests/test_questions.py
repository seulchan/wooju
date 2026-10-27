from pathlib import Path

from brain_core.index import BrainIndex
from wooju_agents.llm import LLMResult
from wooju_agents.questions import make_questions


class Fake:
    name, model = "fake", "fake"

    def __init__(self, data):
        self.data, self.calls = data, []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user))
        return LLMResult(self.data, "", 0, self.name, self.model)


def _index(tmp_path: Path) -> BrainIndex:
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    for slug, title, body in [
        ("compound", "복리", "이자에 이자가 붙는다."),
        ("habit", "습관", "작은 행동이 반복되며 쌓인다."),
    ]:
        (tmp_path / "wiki" / "concepts" / f"{slug}.md").write_text(
            f"---\ntitle: {title}\n---\n# {title}\n\n{body}\n", encoding="utf-8"
        )
    index = BrainIndex()
    index.scan(tmp_path)
    return index


def test_questions_only_and_connections_are_checked(tmp_path):
    index = _index(tmp_path)
    provider = Fake(
        {
            "questions": [
                {"kind": "why", "text": "왜 시간이 길수록 차이가 커질까?"},
                {"kind": "connect", "text": "습관과 어떻게 닮았을까?", "other": 1},
                {"kind": "connect", "text": "없는 노트와는?", "other": 7},
                {"kind": "limits", "text": "왜 시간이 길수록 차이가 커질까?"},
            ]
        }
    )
    qs = make_questions(
        index.get("wiki/concepts/compound"),
        [index.get("wiki/concepts/habit")],
        provider,
        language="ko",
    )
    assert [(q.kind, q.related.id if q.related else None) for q in qs] == [
        ("why", None),
        ("connect", "wiki/concepts/habit"),
    ]
    system, user = provider.calls[0]
    assert "Never answer" in system and "Korean" in system
    assert "[1] 습관" in user


def test_bad_shape_gives_no_questions(tmp_path):
    index = _index(tmp_path)
    assert (
        make_questions(index.get("wiki/concepts/compound"), [], Fake({"x": 1}), language="en") == []
    )
