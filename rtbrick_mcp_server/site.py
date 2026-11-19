"""HTTP access to rtbrick.com: host allowlist, safe fetching, and an on-disk cache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__

log = logging.getLogger("rtbrick_mcp")

DOCS_ROOT = "https://www.rtbrick.com/docs/"
WEBSITE_URL = "https://www.rtbrick.com/"

# documents.rtbrick.com is the old docs host; it now redirects to www.rtbrick.com/docs/.
ALLOWED_HOSTS = frozenset({"www.rtbrick.com", "rtbrick.com", "documents.rtbrick.com"})

MAX_REDIRECTS = 5
_TEXT_CONTENT_TYPES = ("html", "xml", "text", "json")
_CHARSET = re.compile(r"charset=([\w.-]+)", re.IGNORECASE)


class FetchError(Exception):
    """A page could not be fetched. The message is safe to show to the model."""


def validate_url(url: str) -> str:
    """Return the URL without its fragment, or raise FetchError if it is not allowed."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise FetchError(f"Only https:// URLs are allowed, got {url!r}.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise FetchError(
            f"Host {host!r} is not allowed. Allowed hosts: {', '.join(sorted(ALLOWED_HOSTS))}."
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise FetchError(f"Malformed URL {url!r}: {exc}") from exc
    if parsed.username or parsed.password or port not in (None, 443):
        raise FetchError(f"URLs with credentials or a non-standard port are not allowed: {url!r}.")
    return parsed._replace(fragment="").geturl()


class HttpFetcher:
    """GET text pages from allowed hosts, re-checking every redirect hop and capping size."""

    def __init__(
        self,
        timeout: float = 20.0,
        max_retries: int = 3,
        max_bytes: int = 10_000_000,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_bytes = max_bytes
        self._local = threading.local()

    def _session(self) -> requests.Session:
        # requests.Session is not guaranteed thread-safe, so keep one per thread.
        session = getattr(self._local, "session", None)
        if session is None:
            retry = Retry(
                total=self.max_retries,
                backoff_factor=0.5,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                raise_on_status=False,
            )
            session = requests.Session()
            session.mount("https://", HTTPAdapter(max_retries=retry))
            session.headers["User-Agent"] = (
                f"rtbrick-mcp-server/{__version__} (+https://github.com/rtbrick/rtb-mcp)"
            )
            self._local.session = session
        return session

    def get(self, url: str) -> str:
        current = validate_url(url)
        for _ in range(MAX_REDIRECTS + 1):
            try:
                resp = self._session().get(
                    current, timeout=self.timeout, allow_redirects=False, stream=True
                )
            except requests.RequestException as exc:
                raise FetchError(f"Request to {current} failed: {exc}") from exc
            with resp:
                if resp.is_redirect:
                    target = urljoin(current, resp.headers.get("Location", ""))
                    try:
                        current = validate_url(target)
                    except FetchError as exc:
                        raise FetchError(f"{url} redirected to a disallowed URL: {exc}") from exc
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"HTTP {resp.status_code} for {current}")
                content_type = resp.headers.get("Content-Type", "").lower()
                if not any(t in content_type for t in _TEXT_CONTENT_TYPES):
                    raise FetchError(f"Unsupported content type {content_type!r} for {current}")
                body = self._read_capped(resp, current)
                match = _CHARSET.search(content_type)
                encoding = match.group(1) if match else "utf-8"
                try:
                    return body.decode(encoding, errors="replace")
                except LookupError:
                    return body.decode("utf-8", errors="replace")
        raise FetchError(f"Too many redirects starting from {url}")

    def _read_capped(self, resp: requests.Response, url: str) -> bytes:
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > self.max_bytes:
                raise FetchError(f"{url} is larger than the {self.max_bytes}-byte limit")
            chunks.append(chunk)
        return b"".join(chunks)


class DiskCache:
    """JSON records on disk keyed by string. A cache with no directory stores nothing."""

    def __init__(self, directory: Optional[Path]) -> None:
        self.directory = directory
        if directory is not None:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.warning("Disk cache disabled, cannot create %s: %s", directory, exc)
                self.directory = None

    def _path(self, key: str) -> Path:
        assert self.directory is not None
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / digest[:2] / f"{digest}.json"

    def get(self, key: str, max_age: Optional[float]) -> Optional[Any]:
        """Return the stored value, or None if missing or older than max_age seconds."""
        if self.directory is None:
            return None
        try:
            with open(self._path(key), encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            return None
        if record.get("key") != key:
            return None
        if max_age is not None and time.time() - record.get("stored_at", 0) > max_age:
            return None
        return record.get("data")

    def put(self, key: str, data: Any) -> None:
        if self.directory is None:
            return
        path = self._path(key)
        tmp = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"key": key, "stored_at": time.time(), "data": data}, fh)
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("Could not write cache entry for %s: %s", key, exc)
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
