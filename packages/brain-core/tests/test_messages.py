from brain_core.history import HistoryError
from brain_core.messages import MESSAGES, render


def test_every_message_has_both_languages_and_same_placeholders():
    import string

    for key, (ko, en) in MESSAGES.items():
        assert ko and en, key
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
        assert fields(ko) == fields(en), key


def test_render():
    assert render("history.first", "en") == "The first entry of a Brain can't be undone."
    assert (
        render("llm.model_missing", "ko", model="qwen3.5:4b")
        == "AI 모델(qwen3.5:4b)을 아직 받지 않았어요."
    )
    assert render("A plain sentence.", "en") == "A plain sentence."


def test_history_error_is_localized():
    err = HistoryError("history.changed_again", path="a.md")
    assert err.localized("ko").startswith("'a.md'")
    assert "changed again" in str(err)
