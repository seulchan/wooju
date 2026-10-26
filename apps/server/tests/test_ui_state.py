"""Tests for the UI-only state layer (app/ui_state.py).

The UI state is presentation state persisted *outside* the Brain. These tests
cover loading, first-run defaults, corrupt/invalid handling, and atomic writes.
"""

from __future__ import annotations

from app import ui_state


def test_first_run_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(tmp_path / "does-not-exist.json"))
    state = ui_state.load()
    assert state.last_seen_at is None
    assert state.known == []


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    path = tmp_path / "dep" / "state.json"
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(path))
    ui_state.save(ui_state.UiState(last_seen_at="2026-08-08T21:35:12+07:00", known=["a", "b"]))
    loaded = ui_state.load()
    assert loaded.last_seen_at == "2026-08-08T21:35:12+07:00"
    assert loaded.known == ["a", "b"]
    assert path.exists()  # created atomically under WOOJU_UI_STATE_PATH


def test_corrupt_json_degrades_to_first_run(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{ not valid json !", encoding="utf-8")
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(path))
    assert ui_state.load() == ui_state.UiState()


def test_non_dict_json_degrades_to_first_run(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(path))
    assert ui_state.load() == ui_state.UiState()


def test_invalid_last_seen_at_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"last_seen_at": "not-a-date", "known": ["x"]}', encoding="utf-8")
    monkeypatch.setenv("WOOJU_UI_STATE_PATH", str(path))
    state = ui_state.load()
    assert state.last_seen_at is None  # invalid -> first-run semantics
    assert state.known == ["x"]  # valid fields are still honored


def test_parse_isodate_validates(monkeypatch, tmp_path):
    assert ui_state.parse_isodate("2026-08-08T21:35:12+07:00") is not None
    assert ui_state.parse_isodate("2026-08-08T14:35:12Z") is not None
    assert ui_state.parse_isodate("garbage") is None
    assert ui_state.parse_isodate(None) is None
    assert ui_state.parse_isodate("") is None