from datetime import datetime

from app import digest
from app.api.models import AttentionGroup, AttentionItem, AttentionResponse


def item(title):
    return AttentionItem(id=title, path=f"{title}.md", title=title, category="knowledge")


def test_last_send_time_is_the_latest_sunday_evening():
    assert digest.last_send_time(datetime(2026, 11, 1, 18, 0)) == datetime(2026, 11, 1, 18, 0)
    assert digest.last_send_time(datetime(2026, 11, 1, 17, 59)) == datetime(2026, 10, 25, 18, 0)
    assert digest.last_send_time(datetime(2026, 11, 4, 9, 0)) == datetime(2026, 11, 1, 18, 0)


def test_compose_lists_a_few_titles_and_says_nothing_when_quiet():
    quiet = AttentionResponse(groups=[], total=0)
    assert digest.compose(quiet, "en") is None
    busy = AttentionResponse(
        groups=[
            AttentionGroup(
                key="review_due",
                label="Due for review",
                count=5,
                items=[item(t) for t in "ABCDE"],
            ),
            AttentionGroup(key="conflicts", label="Conflicts", count=1, items=[item("X")]),
            AttentionGroup(key="provisional", label="Provisional", count=2, items=[]),
        ],
        total=8,
    )
    text = digest.compose(busy, "ko")
    assert text.splitlines()[0] == "이번 주 Wooju"
    assert "• 다시 볼 노트 5개: A, B, C 외 2개" in text
    assert "• 다른 노트와 어긋나는 자료 1개: X" in text
    assert "Provisional" not in text and "잠정" not in text
