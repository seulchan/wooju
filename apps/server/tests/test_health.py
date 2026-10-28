"""Tests for GET /api/health and Brain path handling."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_health_ok_for_valid_brain_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(tmp_path))
    with TestClient(app) as client:
        data = client.get("/api/health").json()

    assert data["status"] == "ok"
    assert data["api"] == "ok"
    assert data["brain_configured"] is True
    assert data["brain_exists"] is True
    assert data["brain_is_directory"] is True
    assert data["brain_valid"] is True
    assert Path(data["brain_path"]) == tmp_path.resolve()


def test_empty_brain_is_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(tmp_path))
    with TestClient(app) as client:
        data = client.get("/api/health").json()

    assert data["brain_valid"] is True
    assert data["status"] == "ok"


def test_health_when_brain_path_not_set(monkeypatch):
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    with TestClient(app) as client:
        data = client.get("/api/health").json()

    assert data["status"] == "misconfigured"
    assert data["brain_configured"] is False
    assert data["brain_valid"] is False
    assert data["brain_path"] is None
    assert "No Brain folder" in data["message"]


def test_health_when_brain_path_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(missing))
    with TestClient(app) as client:
        data = client.get("/api/health").json()

    assert data["status"] == "misconfigured"
    assert data["brain_configured"] is True
    assert data["brain_exists"] is False
    assert data["brain_is_directory"] is False
    assert data["brain_valid"] is False
    assert "does not exist" in data["message"]


def test_health_when_brain_path_is_a_file(tmp_path, monkeypatch):
    brain_file = tmp_path / "brain.txt"
    brain_file.write_text("not a directory")
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(brain_file))
    with TestClient(app) as client:
        data = client.get("/api/health").json()

    assert data["status"] == "misconfigured"
    assert data["brain_exists"] is True
    assert data["brain_is_directory"] is False
    assert data["brain_valid"] is False
    assert "not a directory" in data["message"]


def test_health_returns_200_even_when_misconfigured(monkeypatch):
    # The endpoint reports status; it never fails the HTTP request.
    monkeypatch.delenv("WOOJU_BRAIN_PATH", raising=False)
    with TestClient(app) as client:
        resp = client.get("/api/health")

    assert resp.status_code == 200


def test_health_never_mutates_brain(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    canary = brain / "CANARY.md"
    canary.write_text("do-not-touch")
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(brain))

    with TestClient(app) as client:
        client.get("/api/health")

    assert canary.read_text() == "do-not-touch"
    assert list(brain.iterdir()) == [canary]


def test_only_requests_addressed_to_this_mac_are_answered(tmp_path, monkeypatch):
    """A web page that points its own name at 127.0.0.1 gets nothing."""
    monkeypatch.setenv("WOOJU_BRAIN_PATH", str(tmp_path))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health", headers={"Host": "127.0.0.1:48731"}).status_code == 200
        assert client.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 400


def test_setup_reports_the_build():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        body = c.get("/api/setup").json()
    assert body["version"] and body["build"]  # "dev" when run from source
