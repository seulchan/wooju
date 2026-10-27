from brain_core.index import BrainIndex
from wooju_agents.llm import LLMResult
from wooju_agents.topics import TopicError, make_topic


class Fake:
    name, model = "fake", "fake-1"

    def __init__(self, data):
        self.data, self.calls = data, []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user))
        return LLMResult(self.data, "", 0.1, self.name, self.model)


def _members(tmp_path):
    for rel, title in {"sources/a.md": "2026년 7월 인상", "sources/b.md": "8월 연속 인상"}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"---\ntitle: {title}\nsource_type: article\ncanonical_ref: x\n---\n# {title}\n\n본문\n",
            encoding="utf-8",
        )
    index = BrainIndex()
    index.scan(tmp_path)
    return [index.get("sources/a"), index.get("sources/b")]


def test_topic_note_names_the_subject_and_links_its_sources(tmp_path):
    provider = Fake(
        {
            "title": "한국은행 기준금리 ",
            "summary": [
                {
                    "text": "한국은행은 2026 년 7월과 8월 연속으로 금리를 올렸다.",
                    "sources": [1, 2, 9],
                },
                {"text": "8월 수준은 확인되지 않았다.", "sources": [2]},
            ],
        }
    )
    note = make_topic(_members(tmp_path), provider, language="ko", path="wiki/overviews/bok.md")
    assert note.title == "한국은행 기준금리"
    assert note.body.startswith("# 한국은행 기준금리\n\n")
    assert "2026년 7월" in note.body  # Korean spacing fixed
    assert (
        "([2026년 7월 인상](../../sources/a.md), [8월 연속 인상](../../sources/b.md))" in note.body
    )
    assert "sources/9" not in note.body  # a number that is not a note is dropped
    assert "Korean" in provider.calls[0][0]


def test_bad_output_is_a_clear_error(tmp_path):
    try:
        make_topic(
            _members(tmp_path),
            Fake({"title": "", "summary": []}),
            language="en",
            path="wiki/overviews/x.md",
        )
    except TopicError as exc:
        assert exc.key == "topic.bad_shape"
    else:
        raise AssertionError("expected TopicError")
