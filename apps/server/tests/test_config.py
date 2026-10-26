"""Tests for Brain path resolution."""

from app.config import ENV_VAR, resolve_brain_path


def test_resolve_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_brain_path() is None


def test_resolve_returns_none_when_blank(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "   ")
    assert resolve_brain_path() is None


def test_resolve_resolves_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    assert resolve_brain_path() == tmp_path.resolve()


def test_resolve_strips_surrounding_whitespace(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, f"  {tmp_path}  ")
    assert resolve_brain_path() == tmp_path.resolve()
