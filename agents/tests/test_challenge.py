from datetime import date
from pathlib import Path

import pytest

from brain_core.changes import apply_proposal
from brain_core.history import ensure_repo
from brain_core.index import BrainIndex
from brain_core.validate import validate_brain
from wooju_agents.challenge import ChallengeError, challenge_insight, insert_challenge
from wooju_agents.llm import LLMResult

INSIGHT = """---
title: 자사주 많은 기업의 재평가
origin: synthesis
insight_kind: hypothesis
status: candidate
derived_from:
  - "[[concepts/treasury]]"
---
# 자사주 많은 기업의 재평가

## Insight

자사주 소각 의무화로 자사주가 많은 저PBR 기업이 재평가될 수 있다.

## Assessment

- 현재 상태: candidate
"""

DRAFT = {
    "wrong_if": ["주주총회 승인으로 보유가 계속 허용되면 [2]"],
    "counter_evidence": ["시장이 이미 반영했을 수 있다 [2]."],
    "scope_limits": [],
    "stale_or_missing": ["주가 반응 데이터가 없다"],
    "restatement": False,
    "verdict": "keep_candidate",
    "reason": "전제는 지지되지만 검증 근거가 없다 [1].",
}


class Fake:
    name, model = "fake", "fake-1"

    def __init__(self, data):
        self.data, self.calls = data, []

    def generate_json(self, system, user, schema):
        self.calls.append((system, user, schema))
        return LLMResult(self.data, "", 0.1, self.name, self.model)


@pytest.fixture
def brain(tmp_path: Path) -> Path:
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "questions").mkdir(parents=True)
    (tmp_path / "sources").mkdir()
    (tmp_path / "wiki" / "concepts" / "treasury.md").write_text(
        "---\ntitle: 자사주 소각\n---\n# 자사주 소각\n\n## 정의\n\n자사주는 1년 안에 소각해야 한다.\n",
        encoding="utf-8",
    )
    (tmp_path / "sources" / "market.md").write_text(
        "---\ntitle: 자사주 테마 주가\nsource_type: news\ncanonical_ref: x\n---\n# 자사주 테마 주가\n\n"
        "## 핵심 내용\n\n- 법 통과 전에 자사주 많은 기업 주가가 먼저 올랐다. 소각 기대가 반영됐다.\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "questions" / "rerating.md").write_text(INSIGHT, encoding="utf-8")
    ensure_repo(tmp_path)
    return tmp_path


def _index(brain: Path) -> BrainIndex:
    i = BrainIndex()
    i.scan(brain)
    return i


def test_challenge_adds_section_with_links_and_passes_validation(brain):
    provider = Fake(DRAFT)
    p = challenge_insight(
        brain,
        _index(brain),
        "wiki/questions/rerating",
        provider,
        language="ko",
        today=date(2026, 10, 26),
    )
    assert p.approval == "batch" and p.agent == "challenger"
    assert p.summary.startswith("후보로 유지")
    text = p.changes[0].content
    assert text.index("## Challenge") < text.index("## Assessment")
    assert "[자사주 소각](../concepts/treasury.md)" in text  # [1] = derived_from first
    assert "[자사주 테마 주가](../../sources/market.md)" in text
    assert "판정 (Challenger 검토, 2026-10-26): 후보로 유지" in text
    assert "status: candidate" in text  # status untouched
    assert '"agent": "challenger", "did": "challenge", "on": "2026-10-26"' in text
    user = provider.calls[0][1]
    assert user.index("[1] 자사주 소각") < user.index("[2] 자사주 테마 주가")

    apply_proposal(brain, p)
    assert not [e for e in validate_brain(brain).errors if "rerating" in e.path]


def test_existing_challenge_is_kept(brain):
    text = insert_challenge(
        "# T\n\n## Challenge\n\n- 기존 메모\n\n## Assessment\n\n- x\n",
        ["- 새 판정"],
        heading_note="Challenger 검토 2026-10-26",
    )
    assert "- 기존 메모\n\n### Challenger 검토 2026-10-26\n\n- 새 판정\n\n## Assessment" in text


def test_only_insights(brain):
    with pytest.raises(ChallengeError) as err:
        challenge_insight(brain, _index(brain), "sources/market", Fake(DRAFT), language="ko")
    assert err.value.key == "challenge.not_insight"
