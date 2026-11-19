import time

import pytest
import requests

from rtbrick_mcp_server.site import DiskCache, FetchError, HttpFetcher, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.rtbrick.com/docs/techdocs/current/index.html",
        "https://rtbrick.com/",
        "https://documents.rtbrick.com/techdocs/current/index.html",
    ],
)
def test_allowed_urls(url):
    assert validate_url(url + "#frag") == url


@pytest.mark.parametrize(
    "url, message",
    [
        ("http://www.rtbrick.com/", "Only https://"),
        ("https://www.youtube.com/watch?v=1", "not allowed"),
        ("https://www.rtbrick.com.evil.example/", "not allowed"),
        ("https://user:pw@www.rtbrick.com/", "credentials"),
        ("https://www.rtbrick.com:8443/", "non-standard port"),
        ("file:///etc/passwd", "Only https://"),
    ],
)
def test_rejected_urls(url, message):
    with pytest.raises(FetchError, match=message):
        validate_url(url)


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status_code = status
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.body = body

    @property
    def is_redirect(self):
        return "Location" in self.headers and self.status_code in (301, 302, 303, 307, 308)

    def iter_content(self, chunk_size):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.requested = []

    def get(self, url, **kwargs):
        assert kwargs["allow_redirects"] is False
        self.requested.append(url)
        return self.responses[url]


def _fetcher(responses, **kwargs):
    fetcher = HttpFetcher(**kwargs)
    session = FakeSession(responses)
    fetcher._session = lambda: session  # type: ignore[method-assign]
    return fetcher, session


def test_follows_allowed_redirects():
    fetcher, session = _fetcher({
        "https://documents.rtbrick.com/a": FakeResponse(301, {"Location": "https://www.rtbrick.com/docs/a"}),
        "https://www.rtbrick.com/docs/a": FakeResponse(body="héllo".encode()),
    })
    assert fetcher.get("https://documents.rtbrick.com/a") == "héllo"
    assert session.requested == ["https://documents.rtbrick.com/a", "https://www.rtbrick.com/docs/a"]


def test_rejects_redirect_to_other_host():
    fetcher, session = _fetcher({
        "https://www.rtbrick.com/go": FakeResponse(302, {"Location": "https://evil.example/x"}),
    })
    with pytest.raises(FetchError, match="redirected to a disallowed URL"):
        fetcher.get("https://www.rtbrick.com/go")
    assert session.requested == ["https://www.rtbrick.com/go"]


def test_rejects_oversized_and_binary_responses():
    fetcher, _ = _fetcher({"https://www.rtbrick.com/big": FakeResponse(body=b"x" * 2000)}, max_bytes=1000)
    with pytest.raises(FetchError, match="larger than"):
        fetcher.get("https://www.rtbrick.com/big")
    fetcher, _ = _fetcher({
        "https://www.rtbrick.com/f.pdf": FakeResponse(headers={"Content-Type": "application/pdf"}),
    })
    with pytest.raises(FetchError, match="Unsupported content type"):
        fetcher.get("https://www.rtbrick.com/f.pdf")


def test_body_read_failures_become_fetch_errors():
    class BrokenBody(FakeResponse):
        def iter_content(self, chunk_size):
            yield b"<html>partial"
            raise requests.exceptions.ChunkedEncodingError("connection reset mid-body")

    fetcher, _ = _fetcher({"https://www.rtbrick.com/x": BrokenBody()})
    with pytest.raises(FetchError, match="Reading https://www.rtbrick.com/x failed"):
        fetcher.get("https://www.rtbrick.com/x")


def test_http_errors_are_reported():
    fetcher, _ = _fetcher({"https://www.rtbrick.com/x": FakeResponse(404)})
    with pytest.raises(FetchError, match="HTTP 404"):
        fetcher.get("https://www.rtbrick.com/x")


def test_disk_cache_round_trip_and_expiry(tmp_path, monkeypatch):
    cache = DiskCache(tmp_path / "cache")
    cache.put("page:a", {"title": "A"})
    assert cache.get("page:a", max_age=60) == {"title": "A"}
    assert cache.get("page:b", max_age=60) is None
    later = time.time() + 120
    monkeypatch.setattr(time, "time", lambda: later)
    assert cache.get("page:a", max_age=60) is None
    assert cache.get("page:a", max_age=None) == {"title": "A"}


def test_disabled_disk_cache_stores_nothing():
    cache = DiskCache(None)
    cache.put("k", 1)
    assert cache.get("k", None) is None
