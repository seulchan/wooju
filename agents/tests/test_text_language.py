from wooju_agents.text import detect_language


def test_detect_language():
    assert (
        detect_language(
            "코스피가 2026년 상반기에 기록적으로 상승했지만 PBR 1배 미만 종목 비율은 오히려 늘었다."
        )
        == "ko"
    )
    assert (
        detect_language(
            "KOSPI rose to a record high in 2026 while the share of stocks below book value grew."
        )
        == "en"
    )
    # Korean prose full of English terms is still Korean.
    assert (
        detect_language(
            "삼성전자 HBM 매출 비중이 30%를 넘으면 valuation re-rating 가능성을 다시 본다. AI server 수요가 핵심이다."
        )
        == "ko"
    )
    assert detect_language("ok") is None


def test_pdf_text_with_a_space_between_every_korean_syllable_is_rejoined():
    from wooju_agents.text import unspace_hangul

    assert unspace_hangul("■ 주 요  뉴 스:  이 란, 종 전  조 건  충 족 을  강 조.") == (
        "■ 주요 뉴스: 이란, 종전 조건 충족을 강조."
    )
    assert (
        unspace_hangul("   ○ 주 가: 미 국  S&P500지 수 는  상 승")
        == "   ○ 주가: 미국 S&P500지수는 상승"
    )
    normal = "   ○ AI 투자, 위험관리 필요하나 구체적 조치와 관련해서는 한계가 존재"
    assert unspace_hangul(normal) == normal  # ordinary Korean is left alone
    assert unspace_hangul("한 국") == "한 국"  # too little to tell
