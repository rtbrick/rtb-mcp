#!/usr/bin/env python3
"""
MIT License
Copyright (c) 2025-2026 Pravin Bhandarkar, RTBrick Inc

RTBrick MCP Server - Website and Documentation Access
Provides tools to access:
  - https://www.rtbrick.com          (main RTBrick website)
  - https://documents.rtbrick.com    (RTBrick technical documentation)
  - https://www.youtube.com          (RTBrick YouTube channel / training videos)

Fixes applied from mcpserver_opt_1.py (original):
  - CONFIG global was never assigned at module level
  - run() had an indentation bug: try/except was at class level, not inside the for loop
  - @lru_cache on an instance method is broken (self is not hashable)
  - load_config() had dead code after sys.exit(1)
  - Docstrings were placed before def statements instead of inside methods

Tools:
  - fetch_rtbrick_page(url)       - fetch any page from allowed RTBrick/YouTube domains
  - get_rtbrick_website()         - get the main rtbrick.com landing page
  - get_tech_docs_index()         - get the tech docs index page
  - search_tech_docs(query)       - search across configured tech docs
  - list_tech_docs()              - list all available tech doc pages
  - get_rtbrick_videos()          - get RTBrick's YouTube playlist / training videos
  - get_youtube_video_info(url)   - fetch metadata for a specific RTBrick YouTube video
"""

import json
import sys
import os
import logging
import traceback
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser
from threading import Lock

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Error: requests library not found. Install with: pip install requests",
          file=sys.stderr)
    sys.exit(1)


# ============================================================================
# Domain allowlist and defaults
# ============================================================================

ALLOWED_DOMAINS = {
    "www.rtbrick.com",
    "rtbrick.com",
    "documents.rtbrick.com",
    "www.youtube.com",
    "youtube.com",
}

RTBRICK_WEBSITE_URL = "https://www.rtbrick.com"
RTBRICK_TECHDOCS_BASE_URL = "https://documents.rtbrick.com/techdocs/current/"
RTBRICK_TECHDOCS_INDEX_URL = "https://documents.rtbrick.com/techdocs/current/index.html"

# RTBrick YouTube training-video playlist
RTBRICK_YOUTUBE_PLAYLIST_URL = (
    "https://www.youtube.com/watch?v=1MhY-1M6Me8"
    "&list=PLIIDQGz9rYDGFlsCUe6YuhQgQXdxyTo6k"
)
# oEmbed endpoint used to retrieve per-video metadata without an API key
_YOUTUBE_OEMBED = "https://www.youtube.com/oembed?url={url}&format=json"

# Default tech-doc paths (relative to RTBRICK_TECHDOCS_BASE_URL).
# Loaded from config.json when available; otherwise these defaults are used.
DEFAULT_TECH_DOC_PATHS: List[str] = [
    "index.html",
    "aclug/acl_intro.html",
    "arpndug/ipneighbor_config.html",
    "bgpug/bgp_intro.html",
    "ctrld/ctrld_overview.html",
    "evpn-vpws/evpn_vpws_intro.html",
    "hqos/hqos_intro.html",
    "interfacesug/interfaces_config.html",
    "interfacesug/interfaces_intro.html",
    "isisug/isis_intro.html",
    "l2xug/l2x_intro.html",
    "l3vpnug/l3vpn_intro.html",
    "lag/lag_config.html",
    "lag/lag_overview.html",
    "lldpug/lldp_intro.html",
    "loggingug/logging_intro.html",
    "ngaccess/access_intro.html",
    "ospf/ospf_intro.html",
    "resmonug/resmon_config_cmds.html",
    "resmonug/resmon_intro.html",
    "resmonug/resmon_operation_cmds.html",
    "tools/manual_installation.html",
    "tsdb/tsdb_intro.html",
]


# ============================================================================
# Configuration
# ============================================================================

def load_config() -> Dict[str, Any]:
    """
    Load optional config.json.

    Searches: $CONFIG_PATH env var, cwd/config.json, script-dir/config.json,
    ~/.config/rtb-doc-mcp-server/config.json.

    Returns a dict with at least 'tech_doc_paths'.  Falls back to defaults if
    no config file is found (no fatal error).
    """
    candidates: List[Path] = []

    env_path = os.getenv("CONFIG_PATH")
    if env_path:
        candidates.append(Path(env_path))

    candidates += [
        Path.cwd() / "config.json",
        Path(__file__).parent / "config.json",
        Path.home() / ".config" / "rtb-doc-mcp-server" / "config.json",
    ]

    for path in candidates:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                logging.getLogger("rtbrick_mcp").info(
                    "Loaded config from %s", path
                )
                return data
            except Exception as exc:  # noqa: BLE001
                logging.getLogger("rtbrick_mcp").warning(
                    "Failed to parse %s: %s — using defaults", path, exc
                )

    logging.getLogger("rtbrick_mcp").info(
        "No config.json found; using built-in defaults"
    )
    return {}


# ============================================================================
# Logging
# ============================================================================

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure structured logging to stderr (keeps stdout clean for JSON-RPC)."""
    logger = logging.getLogger("rtbrick_mcp")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logger.level)
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(funcName)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


# ============================================================================
# HTML text extraction
# ============================================================================

class HTMLTextExtractor(HTMLParser):
    """Strip tags and return readable text, preserving basic structure."""

    BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}
    SKIP_TAGS = {"script", "style", "nav", "footer", "header"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip_depth = 0
        self._in_pre = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "pre":
            self._in_pre = True
            self.parts.append("\n")
        elif tag in self.BLOCK_TAGS or tag == "br":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "pre":
            self._in_pre = False
            self.parts.append("\n")
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_pre:
            self.parts.append(data)
        else:
            text = data.strip()
            if text:
                self.parts.append(text + " ")

    def get_text(self) -> str:
        raw = "".join(self.parts)
        # Collapse runs of blank lines to at most two
        import re
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def extract_text_from_html(html: str) -> str:
    """Return readable plain-text from an HTML document."""
    try:
        parser = HTMLTextExtractor()
        parser.feed(html)
        return parser.get_text()
    except Exception:
        return html[:5000]


# ============================================================================
# Thread-safe document cache with TTL
# ============================================================================

@dataclass
class CacheEntry:
    content: str
    timestamp: datetime
    url: str

    def is_expired(self, ttl_seconds: int) -> bool:
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > ttl_seconds


class DocumentCache:
    """Simple LRU-like cache with TTL expiry."""

    def __init__(self, max_size: int = 200, ttl_seconds: int = 3600) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None or entry.is_expired(self.ttl_seconds):
                if entry:
                    del self._store[key]
                return None
            return entry.content

    def put(self, key: str, content: str, url: str) -> None:
        with self._lock:
            if len(self._store) >= self.max_size and key not in self._store:
                # Evict oldest
                oldest = min(self._store, key=lambda k: self._store[k].timestamp)
                del self._store[oldest]
            self._store[key] = CacheEntry(content=content,
                                           timestamp=datetime.now(),
                                           url=url)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"entries": len(self._store), "max_size": self.max_size}


# ============================================================================
# HTTP client with retries and connection pooling
# ============================================================================

class HTTPClient:
    """requests.Session wrapper with retries and a standard User-Agent."""

    def __init__(self, timeout: int = 30, max_retries: int = 3) -> None:
        self.timeout = timeout
        self.logger = logging.getLogger("rtbrick_mcp")

        retry = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        self.session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=10,
            pool_maxsize=10,
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = "RTBrick-MCP-Server/2.0"

    def get(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (content, error).  One of the two is always None."""
        try:
            self.logger.debug("GET %s", url)
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "").lower()
            if "html" not in ct and "text" not in ct and "json" not in ct:
                return None, f"Unsupported content-type: {ct}"
            self.logger.debug("Fetched %d bytes from %s", len(resp.text), url)
            return resp.text, None
        except requests.exceptions.Timeout:
            msg = f"Timeout ({self.timeout}s) fetching {url}"
            self.logger.error(msg)
            return None, msg
        except requests.exceptions.HTTPError as exc:
            msg = f"HTTP {exc.response.status_code} for {url}"
            self.logger.error(msg)
            return None, msg
        except requests.exceptions.RequestException as exc:
            msg = f"Request error for {url}: {exc}"
            self.logger.error(msg)
            return None, msg

    def close(self) -> None:
        self.session.close()


# ============================================================================
# Simple keyword search with context extraction
# ============================================================================

@dataclass
class SearchHit:
    doc_path: str
    score: float
    match_count: int
    context: str

    def __lt__(self, other: "SearchHit") -> bool:
        return self.score < other.score


def search_documents(
    query: str,
    documents: Dict[str, str],
    context_lines: int = 3,
    max_results: int = 10,
) -> List[SearchHit]:
    """Return scored, ranked search hits."""
    q = query.lower()
    terms = q.split()
    hits: List[SearchHit] = []

    for path, content in documents.items():
        cl = content.lower()
        if q not in cl:
            continue

        match_count = cl.count(q)
        term_score = sum(cl.count(t) for t in terms)
        score = match_count * 10 + term_score
        if q in path.lower():
            score += 50  # filename bonus

        # Extract context snippets
        lines = content.split("\n")
        snippets: List[str] = []
        seen: set = set()
        for i, line in enumerate(lines):
            if q in line.lower():
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                block = "\n".join(lines[start:end])
                h = hash(block[:80])
                if h not in seen:
                    snippets.append(block)
                    seen.add(h)
                if len(snippets) >= 3:
                    break

        hits.append(SearchHit(
            doc_path=path,
            score=score,
            match_count=match_count,
            context="\n\n---\n\n".join(snippets),
        ))

    hits.sort(reverse=True)
    return hits[:max_results]


# ============================================================================
# URL validation
# ============================================================================

def validate_rtbrick_url(url: str) -> Tuple[bool, str]:
    """
    Return (ok, error_message).  ok is True only for URLs whose host is in
    ALLOWED_DOMAINS and whose scheme is https.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, f"Malformed URL: {url!r}"

    if parsed.scheme != "https":
        return False, (
            f"Only https:// URLs are allowed. Got scheme={parsed.scheme!r}. "
            f"Allowed domains: {sorted(ALLOWED_DOMAINS)}"
        )

    host = parsed.netloc.lower().split(":")[0]  # strip optional port
    if host not in ALLOWED_DOMAINS:
        return False, (
            f"Domain {host!r} is not in the RTBrick allowlist. "
            f"Allowed: {sorted(ALLOWED_DOMAINS)}"
        )

    return True, ""


# ============================================================================
# MCP Server
# ============================================================================

class MCPServer:
    """
    JSON-RPC 2.0 / MCP server exposing RTBrick website and documentation tools.

    Tools provided
    --------------
    fetch_rtbrick_page     – fetch any page on an allowed RTBrick/YouTube domain
    get_rtbrick_website    – fetch the main https://www.rtbrick.com landing page
    get_tech_docs_index    – fetch the tech-docs index page
    search_tech_docs       – keyword search across the configured tech-doc pages
    list_tech_docs         – list all configured tech-doc paths
    get_rtbrick_videos     – fetch RTBrick's YouTube training-video playlist info
    get_youtube_video_info – fetch oEmbed metadata for a specific YouTube video URL
    """

    PARSE_ERROR    = -32700
    INVALID_REQ    = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    def __init__(self) -> None:
        self.logger = setup_logging("INFO")

        cfg = load_config()

        # Prefer doc_paths from config; fall back to built-in defaults
        self.tech_doc_paths: List[str] = cfg.get("doc_paths", DEFAULT_TECH_DOC_PATHS)
        self.tech_docs_base_url: str = cfg.get("base_url", RTBRICK_TECHDOCS_BASE_URL)

        self.cache = DocumentCache(max_size=200, ttl_seconds=3600)
        self.http = HTTPClient(timeout=30, max_retries=3)

        self.logger.info(
            "RTBrick MCP Server ready — %d tech-doc paths configured",
            len(self.tech_doc_paths),
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _fetch_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Validate URL, check cache, fetch, parse HTML if needed, re-cache.
        Returns (text_content, error_message).
        """
        ok, err = validate_rtbrick_url(url)
        if not ok:
            return None, err

        cached = self.cache.get(url)
        if cached is not None:
            return cached, None

        raw, err = self.http.get(url)
        if err:
            return None, err

        content = extract_text_from_html(raw) if "<html" in raw.lower() else raw
        self.cache.put(url, content, url)
        return content, None

    def _fetch_tech_doc(self, path: str) -> Tuple[Optional[str], Optional[str]]:
        url = urljoin(self.tech_docs_base_url, path)
        return self._fetch_url(url)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def tool_fetch_rtbrick_page(self, url: str) -> str:
        """Fetch any page from an allowed RTBrick domain."""
        if not url:
            return "Error: 'url' parameter is required."
        content, err = self._fetch_url(url)
        if err:
            return f"Error fetching page: {err}"
        return content

    def tool_get_rtbrick_website(self) -> str:
        """Fetch the main RTBrick website (https://www.rtbrick.com)."""
        content, err = self._fetch_url(RTBRICK_WEBSITE_URL)
        if err:
            return f"Error fetching RTBrick website: {err}"
        return f"# RTBrick Website\nSource: {RTBRICK_WEBSITE_URL}\n\n{content}"

    def tool_get_tech_docs_index(self) -> str:
        """Fetch the RTBrick technical documentation index page."""
        content, err = self._fetch_url(RTBRICK_TECHDOCS_INDEX_URL)
        if err:
            return f"Error fetching tech docs index: {err}"
        return (
            f"# RTBrick Technical Documentation Index\n"
            f"Source: {RTBRICK_TECHDOCS_INDEX_URL}\n\n{content}"
        )

    def tool_search_tech_docs(self, query: str) -> str:
        """Search across all configured tech-doc pages."""
        if not query or not query.strip():
            return "Error: 'query' parameter cannot be empty."

        self.logger.info("search_tech_docs query=%r", query)

        # Lazy-load docs that aren't cached yet
        docs: Dict[str, str] = {}
        errors: List[str] = []
        for path in self.tech_doc_paths:
            content, err = self._fetch_tech_doc(path)
            if content:
                docs[path] = content
            else:
                errors.append(f"{path}: {err}")

        if not docs:
            msg = "No documentation could be loaded."
            if errors:
                msg += "\nErrors:\n" + "\n".join(errors[:5])
            return msg

        hits = search_documents(query, docs)

        if not hits:
            return f"No results found for '{query}' (searched {len(docs)} documents)."

        parts = [
            f"Found {len(hits)} result(s) for '{query}' "
            f"(searched {len(docs)} documents)\n"
        ]
        for i, hit in enumerate(hits, 1):
            url = urljoin(self.tech_docs_base_url, hit.doc_path)
            parts.append(
                f"## Result {i}: {hit.doc_path}\n"
                f"URL: {url}\n"
                f"Score: {hit.score}  |  Matches: {hit.match_count}\n\n"
                f"{hit.context}"
            )
        return "\n\n".join(parts)

    def tool_list_tech_docs(self) -> str:
        """List all configured RTBrick technical documentation pages."""
        lines = [
            "# RTBrick Technical Documentation Pages",
            f"Base URL: {self.tech_docs_base_url}",
            f"Total: {len(self.tech_doc_paths)} pages\n",
        ]
        for i, path in enumerate(self.tech_doc_paths, 1):
            url = urljoin(self.tech_docs_base_url, path)
            cached = " ✓" if self.cache.get(url) else ""
            lines.append(f"{i:>3}. {path}{cached}")
        lines.append(
            "\n(✓ = content cached; use search_tech_docs or fetch_rtbrick_page to load)"
        )
        return "\n".join(lines)

    def tool_get_rtbrick_videos(self) -> str:
        """Return metadata for the RTBrick YouTube training-video playlist."""
        # Fetch oEmbed info for the first/featured video in the playlist
        oembed_url = _YOUTUBE_OEMBED.format(url=RTBRICK_YOUTUBE_PLAYLIST_URL)

        # oEmbed is on youtube.com — validate before fetching
        ok, err = validate_rtbrick_url(oembed_url)
        if not ok:
            return f"Error: {err}"

        raw, err = self.http.get(oembed_url)
        if err:
            return (
                f"Error fetching YouTube metadata: {err}\n\n"
                f"You can view the RTBrick training-video playlist directly at:\n"
                f"{RTBRICK_YOUTUBE_PLAYLIST_URL}"
            )

        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            return (
                f"Could not parse YouTube oEmbed response.\n\n"
                f"RTBrick training-video playlist:\n{RTBRICK_YOUTUBE_PLAYLIST_URL}"
            )

        lines = [
            "# RTBrick YouTube Training Videos",
            f"Playlist URL: {RTBRICK_YOUTUBE_PLAYLIST_URL}",
            "",
            f"**Title:**   {meta.get('title', 'N/A')}",
            f"**Channel:** {meta.get('author_name', 'N/A')}",
            f"**Channel URL:** {meta.get('author_url', 'N/A')}",
            f"**Type:**    {meta.get('type', 'N/A')}",
        ]
        if meta.get("thumbnail_url"):
            lines.append(f"**Thumbnail:** {meta['thumbnail_url']}")
        lines += [
            "",
            "Use `fetch_rtbrick_page` with the playlist URL to browse the page,",
            "or `get_youtube_video_info` with a specific video URL for per-video details.",
        ]
        return "\n".join(lines)

    def tool_get_youtube_video_info(self, url: str) -> str:
        """Fetch oEmbed metadata for a specific RTBrick YouTube video URL."""
        if not url:
            return "Error: 'url' parameter is required."

        ok, err = validate_rtbrick_url(url)
        if not ok:
            return f"Error: {err}"

        oembed_url = _YOUTUBE_OEMBED.format(url=url)
        raw, err = self.http.get(oembed_url)
        if err:
            return f"Error fetching YouTube metadata for {url}: {err}"

        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            return f"Could not parse YouTube oEmbed response for {url}."

        lines = [
            f"# YouTube Video Info",
            f"URL: {url}",
            "",
            f"**Title:**   {meta.get('title', 'N/A')}",
            f"**Channel:** {meta.get('author_name', 'N/A')}",
            f"**Channel URL:** {meta.get('author_url', 'N/A')}",
            f"**Type:**    {meta.get('type', 'N/A')}",
        ]
        if meta.get("thumbnail_url"):
            lines.append(f"**Thumbnail:** {meta['thumbnail_url']}")
        if meta.get("width") and meta.get("height"):
            lines.append(f"**Dimensions:** {meta['width']}×{meta['height']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # MCP protocol handlers
    # ------------------------------------------------------------------

    def _tools_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "fetch_rtbrick_page",
                "description": (
                    "Fetch the content of any page on an allowed domain "
                    "(www.rtbrick.com, documents.rtbrick.com, or www.youtube.com). "
                    "Only https:// URLs on those domains are accepted. "
                    "Note: YouTube pages are JavaScript-rendered; use "
                    "get_rtbrick_videos or get_youtube_video_info for richer metadata."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": (
                                "Full https:// URL on www.rtbrick.com, "
                                "documents.rtbrick.com, or www.youtube.com"
                            ),
                        }
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "get_rtbrick_website",
                "description": (
                    "Fetch the main RTBrick website (https://www.rtbrick.com) "
                    "and return its text content."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_tech_docs_index",
                "description": (
                    "Fetch the RTBrick technical documentation index page at "
                    "https://documents.rtbrick.com/techdocs/current/index.html"
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "search_tech_docs",
                "description": (
                    "Keyword search across all configured RTBrick technical "
                    "documentation pages. Returns ranked results with context snippets."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term or phrase",
                            "minLength": 1,
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "list_tech_docs",
                "description": (
                    "List all configured RTBrick technical documentation pages "
                    "with their relative paths and URLs."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_rtbrick_videos",
                "description": (
                    "Fetch metadata for RTBrick's YouTube training-video playlist "
                    "(https://www.youtube.com/watch?v=1MhY-1M6Me8"
                    "&list=PLIIDQGz9rYDGFlsCUe6YuhQgQXdxyTo6k). "
                    "Returns title, channel name, thumbnail URL, and the playlist link."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_youtube_video_info",
                "description": (
                    "Fetch oEmbed metadata (title, channel, thumbnail) for a specific "
                    "RTBrick YouTube video. Only www.youtube.com URLs are accepted."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": (
                                "Full https://www.youtube.com/watch?v=... URL "
                                "of the RTBrick video"
                            ),
                        }
                    },
                    "required": ["url"],
                },
            },
        ]

    def _ok(self, request_id: Any, text: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    def _error(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        self.logger.error("JSON-RPC error [%d]: %s", code, message)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route one JSON-RPC request. Returns None for notifications."""
        method = request.get("method", "")
        request_id = request.get("id")

        # Notifications have no id — do not respond
        if request_id is None:
            if method == "notifications/initialized":
                self.logger.info("Received initialized notification")
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "logging": {}},
                    "serverInfo": {
                        "name": "rtbrick-mcp-server",
                        "version": "2.0.0",
                    },
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": self._tools_schema()},
            }

        if method == "tools/call":
            params = request.get("params", {})
            tool = params.get("name", "")
            args = params.get("arguments", {})

            try:
                if tool == "fetch_rtbrick_page":
                    url = args.get("url", "").strip()
                    if not url:
                        return self._error(request_id, self.INVALID_PARAMS,
                                           "'url' is required")
                    result = self.tool_fetch_rtbrick_page(url)

                elif tool == "get_rtbrick_website":
                    result = self.tool_get_rtbrick_website()

                elif tool == "get_tech_docs_index":
                    result = self.tool_get_tech_docs_index()

                elif tool == "search_tech_docs":
                    query = args.get("query", "").strip()
                    if not query:
                        return self._error(request_id, self.INVALID_PARAMS,
                                           "'query' is required")
                    result = self.tool_search_tech_docs(query)

                elif tool == "list_tech_docs":
                    result = self.tool_list_tech_docs()

                elif tool == "get_rtbrick_videos":
                    result = self.tool_get_rtbrick_videos()

                elif tool == "get_youtube_video_info":
                    url = args.get("url", "").strip()
                    if not url:
                        return self._error(request_id, self.INVALID_PARAMS,
                                           "'url' is required")
                    result = self.tool_get_youtube_video_info(url)

                else:
                    return self._error(request_id, self.METHOD_NOT_FOUND,
                                       f"Unknown tool: {tool!r}")

                return self._ok(request_id, result)

            except Exception as exc:
                self.logger.exception("Error executing tool %r", tool)
                return self._error(request_id, self.INTERNAL_ERROR,
                                   f"Tool execution failed: {exc}")

        return self._error(request_id, self.METHOD_NOT_FOUND,
                           f"Method not found: {method!r}")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Read JSON-RPC lines from stdin, write responses to stdout."""
        self.logger.info("RTBrick MCP Server starting")

        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                request_id: Any = None
                try:
                    request = json.loads(line)
                    request_id = request.get("id")
                    response = self.handle_request(request)
                    if response is not None:
                        print(json.dumps(response), flush=True)

                except json.JSONDecodeError as exc:
                    self.logger.error("JSON parse error: %s", exc)
                    # Cannot send a response without a valid id
                    if request_id is not None:
                        print(
                            json.dumps(self._error(request_id, self.PARSE_ERROR,
                                                   "Parse error")),
                            flush=True,
                        )

                except Exception as exc:
                    self.logger.exception("Unexpected error processing request")
                    if request_id is not None:
                        print(
                            json.dumps(self._error(request_id, self.INTERNAL_ERROR,
                                                   str(exc))),
                            flush=True,
                        )

        except KeyboardInterrupt:
            self.logger.info("Server interrupted")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Release resources."""
        self.logger.info("Shutting down")
        self.http.close()
        self.cache.clear()


# ============================================================================
# Entry point
# ============================================================================

if __name__ == "__main__":
    try:
        server = MCPServer()
        server.run()
    except Exception as exc:
        print(f"Fatal startup error: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
