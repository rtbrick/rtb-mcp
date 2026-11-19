"""RTBrick documentation catalog: versions, page lists, page retrieval and search.

Pages and versions are discovered from the site's sitemaps
(https://www.rtbrick.com/docs/sitemap-<source>.xml), so new guides and releases show up
without code changes.

Tech docs publish every patch release (26.2.1, 26.2.1.1, ... 26.2.1.5). Patches of one
release line differ very little, so the server keeps the newest patch of each of the
most recent release lines (5 by default). Training material has a single "latest" version.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .extract import Page, extract_page
from .search import Hit, SearchIndex
from .site import DOCS_ROOT, DiskCache, FetchError, HttpFetcher, validate_url

log = logging.getLogger("rtbrick_mcp")

SOURCES = {"techdocs": "Technical Documentation", "trainings": "Training"}
CURRENT_SEGMENT = "current"
PINNED_TTL = 30 * 24 * 3600  # numbered versions don't change once published


@dataclass(frozen=True)
class DocVersion:
    source: str
    name: str  # "26.3.1", "26.2.1.5", or "latest" for trainings
    segment: str  # URL path segment: "current" or the version number
    is_current: bool = False

    @property
    def base_url(self) -> str:
        return f"{DOCS_ROOT}{self.source}/{self.segment}/"

    @property
    def label(self) -> str:
        numbered = version_key(self.name) is not None
        return f"{self.name} (current)" if self.is_current and numbered else self.name


@dataclass
class Catalog:
    versions: List[DocVersion]
    pages: Dict[str, List[str]]  # URL segment -> page paths relative to the version root
    loaded_at: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    hits: List[Hit]
    searched: List[DocVersion]


def version_key(name: str) -> Optional[Tuple[int, ...]]:
    try:
        return tuple(int(part) for part in name.split("."))
    except ValueError:
        return None


def parse_sitemap(xml_text: str, source: str) -> Dict[str, List[str]]:
    """Map each version segment to the HTML pages the sitemap lists for it."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    prefix = f"{DOCS_ROOT}{source}/"
    pages: Dict[str, set] = defaultdict(set)
    for el in root.iter():
        if not el.tag.endswith("loc") or not el.text:
            continue
        url = el.text.strip()
        if not url.startswith(prefix):
            continue
        segment, _, path = url[len(prefix) :].partition("/")
        if segment and path.endswith(".html"):
            pages[segment].add(path)
    return {segment: sorted(paths) for segment, paths in pages.items()}


def parse_current_version(index_html: str, source: str) -> Optional[str]:
    """Read the real version number of the 'current' alias from its index page."""
    match = re.search(
        rf'data-component="{re.escape(source)}"\s+data-version="([^"]+)"', index_html
    )
    return match.group(1) if match else None


def select_versions(
    source: str, segments: Iterable[str], current_name: str, max_versions: int
) -> List[DocVersion]:
    """Newest patch of each release line (first three version numbers), newest first."""
    current_key = version_key(current_name)
    candidates: List[Tuple[Tuple[int, ...], DocVersion]] = []
    for segment in segments:
        if segment == CURRENT_SEGMENT:
            # Unnumbered current versions (trainings' "latest") sort above everything.
            key = current_key or (10**9,)
            candidates.append((key, DocVersion(source, current_name, segment, is_current=True)))
            continue
        key = version_key(segment)
        if key is None or key == current_key:
            continue  # not a release, or a numbered duplicate of the current alias
        candidates.append((key, DocVersion(source, segment, segment)))

    newest_per_line: Dict[Tuple[int, ...], Tuple[Tuple[int, ...], DocVersion]] = {}
    for key, version in candidates:
        line = key[:3]
        if line not in newest_per_line or key > newest_per_line[line][0]:
            newest_per_line[line] = (key, version)
    ordered = sorted(newest_per_line.values(), key=lambda kv: kv[0], reverse=True)
    return [version for _, version in ordered[:max_versions]]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


class DocsLibrary:
    def __init__(
        self,
        fetcher: HttpFetcher,
        cache: DiskCache,
        *,
        max_versions: int = 5,
        ttl_seconds: float = 24 * 3600,
        workers: int = 8,
    ) -> None:
        self.fetcher = fetcher
        self.cache = cache
        self.max_versions = max(1, max_versions)
        self.ttl_seconds = ttl_seconds
        self.workers = max(1, workers)
        self._lock = threading.Lock()
        self._catalogs: Dict[str, Catalog] = {}
        self._indexes: Dict[DocVersion, Tuple[float, SearchIndex]] = {}
        self._index_locks: Dict[DocVersion, threading.Lock] = {}

    @classmethod
    def from_env(cls) -> "DocsLibrary":
        cache_setting = os.getenv("RTBRICK_MCP_CACHE_DIR")
        if cache_setting is None:
            base = os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
            cache_dir: Optional[Path] = Path(base) / "rtbrick-mcp"
        elif cache_setting.strip().lower() in ("", "off", "none"):
            cache_dir = None
        else:
            cache_dir = Path(cache_setting).expanduser()
        return cls(
            HttpFetcher(),
            DiskCache(cache_dir),
            max_versions=_env_int("RTBRICK_MCP_MAX_VERSIONS", 5),
            ttl_seconds=_env_int("RTBRICK_MCP_CACHE_TTL_HOURS", 24) * 3600,
            workers=_env_int("RTBRICK_MCP_WORKERS", 8),
        )

    # -- fetching --------------------------------------------------------------

    def _fetch_text(self, url: str, max_age: float) -> str:
        key = f"text:{url}"
        cached = self.cache.get(key, max_age)
        if cached is not None:
            return cached
        try:
            text = self.fetcher.get(url)
        except FetchError:
            stale = self.cache.get(key, None)
            if stale is None:
                raise
            log.warning("Using stale cached copy of %s", url)
            return stale
        self.cache.put(key, text)
        return text

    def get_page_by_url(self, url: str, max_age: Optional[float] = None) -> Page:
        url = validate_url(url)
        if max_age is None:
            max_age = self.ttl_seconds
        key = f"page:{url}"
        cached = self.cache.get(key, max_age)
        if cached is not None:
            return Page.from_dict(cached)
        try:
            html = self.fetcher.get(url)
        except FetchError:
            stale = self.cache.get(key, None)
            if stale is None:
                raise
            log.warning("Using stale cached copy of %s", url)
            return Page.from_dict(stale)
        page = extract_page(html, url)
        self.cache.put(key, page.to_dict())
        return page

    # -- catalog ---------------------------------------------------------------

    def catalog(self, source: str) -> Catalog:
        if source not in SOURCES:
            raise ValueError(f"Unknown source {source!r}. Use one of: {', '.join(SOURCES)}.")
        with self._lock:
            cat = self._catalogs.get(source)
            if cat is not None and time.time() - cat.loaded_at < self.ttl_seconds:
                return cat
        sitemap = self._fetch_text(f"{DOCS_ROOT}sitemap-{source}.xml", self.ttl_seconds)
        pages = parse_sitemap(sitemap, source)
        if not pages:
            raise FetchError(f"The {source} sitemap lists no pages.")
        current_name = CURRENT_SEGMENT
        if CURRENT_SEGMENT in pages:
            try:
                index = self._fetch_text(
                    f"{DOCS_ROOT}{source}/{CURRENT_SEGMENT}/index.html", self.ttl_seconds
                )
                current_name = parse_current_version(index, source) or CURRENT_SEGMENT
            except FetchError as exc:
                log.warning("Could not read the current %s version: %s", source, exc)
        versions = select_versions(source, pages, current_name, self.max_versions)
        cat = Catalog(versions=versions, pages=pages)
        with self._lock:
            self._catalogs[source] = cat
        log.info("%s versions: %s", source, ", ".join(v.label for v in versions))
        return cat

    def resolve(self, source: str, version: Optional[str]) -> DocVersion:
        """Match 'current'/None, an exact version, or a release-line prefix like '26.2'."""
        versions = self.catalog(source).versions
        wanted = (version or "").strip()
        if wanted.lower() in ("", "current", "latest"):
            return next((v for v in versions if v.is_current), versions[0])
        for v in versions:
            if v.name == wanted:
                return v
        for v in versions:  # newest first, so the first prefix match is the newest patch
            if v.name.startswith(wanted + "."):
                return v
        raise ValueError(
            f"Version {version!r} is not available for {source}. "
            f"Available: {', '.join(v.label for v in versions)}."
        )

    def pages(self, version: DocVersion) -> List[str]:
        return self.catalog(version.source).pages.get(version.segment, [])

    def _max_age(self, version: DocVersion) -> float:
        return self.ttl_seconds if version.is_current else PINNED_TTL

    def get_page(self, version: DocVersion, path: str) -> Page:
        path = path.strip().lstrip("/")
        if not path or ".." in path.split("/"):
            raise ValueError(f"Invalid page path {path!r}.")
        return self.get_page_by_url(version.base_url + path, self._max_age(version))

    # -- search ----------------------------------------------------------------

    def index(self, version: DocVersion) -> SearchIndex:
        with self._lock:
            lock = self._index_locks.setdefault(version, threading.Lock())
        with lock:
            entry = self._indexes.get(version)
            if entry and time.time() - entry[0] < self._max_age(version):
                return entry[1]
            paths = self.pages(version)
            started = time.time()
            idx = SearchIndex()
            failures = 0
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {pool.submit(self.get_page, version, p): p for p in paths}
                for future in as_completed(futures):
                    try:
                        page = future.result()
                    except (FetchError, ValueError) as exc:
                        failures += 1
                        log.warning("Skipping %s: %s", futures[future], exc)
                        continue
                    idx.add_page(page, version.source, version.label)
            if not len(idx):
                raise FetchError(f"Could not load any {version.source} {version.label} pages.")
            log.info(
                "Indexed %s %s: %d pages, %d sections, %d failures in %.1fs",
                version.source, version.label, len(paths) - failures, len(idx),
                failures, time.time() - started,
            )
            self._indexes[version] = (time.time(), idx)
            return idx

    def search(
        self,
        query: str,
        source: str = "all",
        version: Optional[str] = None,
        limit: int = 8,
    ) -> SearchResult:
        if source not in ("all", *SOURCES):
            raise ValueError(f"Unknown source {source!r}. Use all, {', '.join(SOURCES)}.")
        targets: List[DocVersion] = []
        if source in ("all", "techdocs"):
            if (version or "").strip().lower() == "all":
                targets.extend(self.catalog("techdocs").versions)
            else:
                targets.append(self.resolve("techdocs", version))
        if source in ("all", "trainings"):
            targets.append(self.resolve("trainings", None))
        hits: List[Hit] = []
        for target in targets:
            hits.extend(self.index(target).search(query, limit))
        hits.sort(key=lambda h: -h.score)
        return SearchResult(hits=hits[:limit], searched=targets)

    def start_prefetch(self) -> None:
        """Index the current tech docs and training material in the background."""

        def run() -> None:
            for source in SOURCES:
                try:
                    self.index(self.resolve(source, None))
                except Exception as exc:  # noqa: BLE001 - background warm-up only
                    log.warning("Prefetch of %s failed: %s", source, exc)

        threading.Thread(target=run, name="rtbrick-prefetch", daemon=True).start()
