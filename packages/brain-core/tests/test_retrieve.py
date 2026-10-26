from pathlib import Path

from brain_core.index import BrainIndex
from brain_core.retrieve import Retriever, passages, tokens


def _brain(tmp_path: Path) -> BrainIndex:
    (tmp_path / "sources").mkdir()
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "sources" / "value-up.md").write_text(
        "---\ntitle: 코리아 밸류업 지수 발표\nsource_type: news\ncanonical_ref: x\n---\n"
        "# 코리아 밸류업 지수 발표\n\n## 핵심 내용\n\n- 한국거래소가 밸류업 지수 구성종목 100개를 발표했다.\n"
        "- 삼성전자와 SK하이닉스가 포함됐다.\n\n## 한계와 주의점\n\n- 편입 기준 논란이 있다.\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "concepts" / "pbr.md").write_text(
        "---\ntitle: Price-to-book ratio\n---\n# Price-to-book ratio\n\n"
        "## Definition\n\nPrice divided by book value per share.\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "concepts" / "fx.md").write_text(
        "---\ntitle: 환율\n---\n# 환율\n\n## 정의\n\n원/달러 환율은 수출 기업 실적에 영향을 준다.\n",
        encoding="utf-8",
    )
    index = BrainIndex()
    index.scan(tmp_path)
    return index


def test_tokens_strip_korean_particles_and_question_words():
    t = tokens("밸류업 지수에 어떤 기업이 들어갔어?")
    assert "지수" in t and "기업" in t
    assert "어떤" not in t
    assert "the" not in tokens("What is the PBR?")


def test_question_finds_passage_without_every_word(tmp_path):
    hits = Retriever(_brain(tmp_path)).search("밸류업 지수에 어떤 기업이 들어갔어?")
    assert hits
    assert hits[0][1].id == "sources/value-up"


def test_best_section_wins(tmp_path):
    r = Retriever(_brain(tmp_path))
    hits = r.search("밸류업 지수 구성종목은 몇 개야?")
    assert hits[0][1].heading == "핵심 내용"
    hits = r.search("밸류업 편입 기준에 문제는 없어?")
    assert hits[0][1].heading == "한계와 주의점"


def test_english_question(tmp_path):
    hits = Retriever(_brain(tmp_path)).search("what does price to book mean")
    assert hits[0][1].id == "wiki/concepts/pbr"


def test_no_match_and_empty(tmp_path):
    r = Retriever(_brain(tmp_path))
    assert r.search("") == []
    assert r.search("cryptocurrency mining") == []


def test_per_note_cap(tmp_path):
    hits = Retriever(_brain(tmp_path)).search("밸류업 편입 기준 지수", per_note=1)
    assert [p.id for _, p in hits].count("sources/value-up") == 1


def test_passages_split_on_sections(tmp_path):
    rec = _brain(tmp_path).get("sources/value-up")
    assert [p.heading for p in passages(rec)] == ["핵심 내용", "한계와 주의점"]
