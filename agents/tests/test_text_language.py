from wooju_agents.text import detect_language


def test_detect_language():
    assert detect_language("코스피가 2026년 상반기에 기록적으로 상승했지만 PBR 1배 미만 종목 비율은 오히려 늘었다.") == "ko"
    assert detect_language("KOSPI rose to a record high in 2026 while the share of stocks below book value grew.") == "en"
    # Korean prose full of English terms is still Korean.
    assert detect_language("삼성전자 HBM 매출 비중이 30%를 넘으면 valuation re-rating 가능성을 다시 본다. AI server 수요가 핵심이다.") == "ko"
    assert detect_language("ok") is None
