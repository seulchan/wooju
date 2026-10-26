import plistlib
import socket
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from brain_core.index import BrainIndex
from wooju_agents import capture
from wooju_agents.capture import (
    CaptureError,
    classify_text,
    fetch,
    link_for,
    read_link_file,
    save_link,
    save_memo,
)
from wooju_agents.ingest import inbox_files

PAGE = (
    b"<html><head><title>Value-up</title></head><body><p>"
    + b"Korea index news. " * 20
    + b"</p></body></html>"
)


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("93.184.216.34", 0))]
    )


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("https://example.com/a", "link"),
        ("이거 나중에 읽기 https://example.com/a", "link"),
        ("삼성전자 HBM 비중이 다음 분기에 30%를 넘을지 확인하자", "memo"),
        ("긴 메모 " * 60 + " https://example.com/a", "memo"),
    ],
)
def test_classify(text, kind):
    assert classify_text(text)[0] == kind


def test_empty_text():
    with pytest.raises(CaptureError):
        classify_text("   ")


def test_memo_is_kept_as_written_and_is_searchable(tmp_path):
    now = datetime(2026, 10, 27, 9, 30, tzinfo=timezone(timedelta(hours=7)))
    rel = save_memo(
        tmp_path, "삼성전자 HBM 비중 확인\n\n다음 분기 실적에서.", via="telegram", now=now
    )
    assert rel == "inbox/memos/2026-10-27-093000.md"
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert "title: 삼성전자 HBM 비중 확인" in text and "via: telegram" in text
    assert text.endswith("다음 분기 실적에서.\n")
    assert save_memo(tmp_path, "x", via="app", now=now).endswith("-2.md")

    index = BrainIndex()
    index.scan(tmp_path)
    assert index.get("inbox/memos/2026-10-27-093000").category == "memory"
    # Memos are never fed to the Ingest agent.
    assert inbox_files(tmp_path) == []


def test_link_is_saved_with_its_address(tmp_path, public_dns):
    def handler(request):
        if request.url.path == "/short":
            return httpx.Response(
                301, headers={"location": "https://news.example.com/2026/value-up.html"}
            )
        return httpx.Response(
            200, content=PAGE, headers={"content-type": "text/html; charset=utf-8"}
        )

    rel = save_link(tmp_path, "https://example.com/short", _client(handler))
    assert rel == "inbox/news-example-com-value-up.html"
    assert link_for(tmp_path, rel) == "https://news.example.com/2026/value-up.html"
    assert inbox_files(tmp_path) == [rel]


def test_pdf_link(tmp_path, public_dns):
    client = _client(
        lambda r: httpx.Response(
            200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"}
        )
    )
    data, suffix, _ = fetch("https://example.com/report", client)
    assert suffix == ".pdf"


def test_private_addresses_are_refused(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda h, p: [(None, None, None, None, ("192.168.0.10", 0))]
    )
    with pytest.raises(CaptureError) as err:
        fetch("http://router.local/admin")
    assert err.value.key == "capture.bad_link"
    with pytest.raises(CaptureError):
        fetch("file:///etc/passwd")


def test_too_big(tmp_path, public_dns, monkeypatch):
    monkeypatch.setattr(capture, "MAX_BYTES", 10)
    client = _client(
        lambda r: httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})
    )
    with pytest.raises(CaptureError) as err:
        fetch("https://example.com/", client)
    assert err.value.key == "capture.too_big"


def test_link_files(tmp_path):
    webloc = tmp_path / "a.webloc"
    webloc.write_bytes(plistlib.dumps({"URL": "https://example.com/x"}))
    assert read_link_file(webloc) == "https://example.com/x"
    url = tmp_path / "b.url"
    url.write_text("[InternetShortcut]\nURL=https://example.com/y\n")
    assert read_link_file(url) == "https://example.com/y"
    bad = tmp_path / "c.url"
    bad.write_text("[InternetShortcut]\nURL=file:///etc/passwd\n")
    with pytest.raises(CaptureError):
        read_link_file(bad)
