"""The weekly Telegram summary: what in the Brain is waiting for the user.

Sent on Sunday evening (local time), or at the first chance after it when the
Mac was asleep. Built only from the "What needs attention?" projection, so it
says nothing the Home screen does not; nothing waiting → no message.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from brain_core.messages import render

from .api.models import AttentionResponse

SEND_WEEKDAY = 6  # Sunday
SEND_HOUR = 18
MAX_TITLES = 3

# Which attention groups the summary mentions, in this order.
_GROUPS = ("review_due", "conflicts", "grounds_changed", "candidate", "open_questions")


def last_send_time(now: datetime) -> datetime:
    """The most recent Sunday 18:00 at or before ``now`` (same time zone)."""
    days_back = (now.weekday() - SEND_WEEKDAY) % 7
    sunday = (now - timedelta(days=days_back)).replace(
        hour=SEND_HOUR, minute=0, second=0, microsecond=0
    )
    return sunday if sunday <= now else sunday - timedelta(days=7)


def is_due(now: datetime, last_sent: datetime | None) -> bool:
    """True once per week, from Sunday 18:00 until it has been sent."""
    if last_sent is None:
        return False  # the first week only starts counting; nothing is sent at once
    return last_sent < last_send_time(now)


def compose(attention: AttentionResponse, language: str, topic_suggestions: int = 0) -> str | None:
    """The message text, or None when nothing is waiting."""
    by_key = {g.key: g for g in attention.groups}
    lines: list[str] = []
    for key in _GROUPS:
        group = by_key.get(key)
        if group is None or not group.count:
            continue
        titles = ", ".join(i.title for i in group.items[:MAX_TITLES])
        more = group.count - min(len(group.items), MAX_TITLES)
        if more > 0:
            titles += render("digest.more", language, n=more)
        lines.append(render(f"digest.{key}", language, n=group.count, titles=titles))
    if topic_suggestions:
        lines.append(render("digest.topics", language, n=topic_suggestions))
    if not lines:
        return None
    head = render("digest.title", language)
    tail = render("digest.open_app", language)
    return "\n".join([head, "", *(f"• {line}" for line in lines), "", tail])
