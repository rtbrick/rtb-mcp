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
from typing import Callable, Dict, Iterable, List, Optional, Tuple, TypeVar

from .extract import Page, to_page
from .search import Hit, SearchIndex
from .site import DOCS_ROOT, DiskCache, FetchError, HttpFetcher, validate_url

log = logging.getLogger("rtbrick_mcp")

SOURCES = {"techdocs": "Technical Documentation", "trainings": "Training"}
CURRENT_SEGMENT = "current"
PINNED_TTL = 30 * 24 * 3600  # numbered versions don't change once published
PARTIAL_INDEX_TTL = 5 * 60  # first retry of pages that failed to load; doubles each time

T = TypeVar("T")


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
class _IndexState:
    index: SearchIndex
    pages: Dict[str, Page]  # pages that loaded, by path
    full_until: float  # after this every page is fetched again
    retry_at: float  # after this only the missing pages are retried (== full_until if none)
    retries: int = 0  # consecutive retries that still left pages missing


@dataclass
class SearchResult:
    hits: List[Hit]
    searched: List[DocVersion]
    skipped: List[str] = field(default_factory=list)  # sources that could not be searched


def version_key(name: str) -> Optional[Tuple[int, ...]]:
    try:
        return tuple(int(part) for part in name.split("."))
    except ValueError:
        return None


def parse_sitemap(xml_text: str, source: str) -> Dict[str, List[str]]:
    """Map each version segment to the HTML pages the sitemap lists for it."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        raise FetchError(f"The {source} sitemap is not valid XML: {exc}") from exc
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
        self._indexes: Dict[DocVersion, _IndexState] = {}
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

    def _fetch_parsed(self, url: str, max_age: float, parse: Callable[[str], T]) -> T:
        """Fetch and parse a text resource; only bodies that parse are cached.

        parse() raises FetchError for content that isn't what we expect (a maintenance
        page instead of a sitemap, say). Such a body is never cached, and the last good
        cached copy is used instead when there is one.
        """
        key = f"text:{url}"
        cached = self.cache.get(key, max_age)
        if cached is not None:
            try:
                return parse(cached)
            except FetchError:
                pass  # unusable cached copy: fetch again
        try:
            text = self.fetcher.get(url)
            result = parse(text)
        except FetchError:
            stale = self.cache.get(key, None)
            if stale is not None:
                try:
                    result = parse(stale)
                except FetchError:
                    pass
                else:
                    log.warning("Using stale cached copy of %s", url)
                    return result
            raise
        self.cache.put(key, text)
        return result

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
        page = to_page(html, url)
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
        def sitemap_pages(text: str) -> Dict[str, List[str]]:
            found = parse_sitemap(text, source)
            if not found:
                raise FetchError(f"The {source} sitemap lists no pages.")
            return found

        def current_version(text: str) -> str:
            name = parse_current_version(text, source)
            if name is None:
                raise FetchError(f"The current {source} index page has no version marker.")
            return name

        pages = self._fetch_parsed(
            f"{DOCS_ROOT}sitemap-{source}.xml", self.ttl_seconds, sitemap_pages
        )
        current_name = CURRENT_SEGMENT
        if CURRENT_SEGMENT in pages:
            try:
                current_name = self._fetch_parsed(
                    f"{DOCS_ROOT}{source}/{CURRENT_SEGMENT}/index.html",
                    self.ttl_seconds,
                    current_version,
                )
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
            now = time.time()
            state = self._indexes.get(version)
            if state and now < state.retry_at:
                return state.index
            paths = self.pages(version)
            # Within the version's lifetime only the pages that failed are fetched again;
            # the ones already loaded are kept in memory (the disk cache may be off).
            keep = state is not None and now < state.full_until
            loaded: Dict[str, Page] = dict(state.pages) if keep and state else {}
            todo = [p for p in paths if p not in loaded]
            failures = 0
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {pool.submit(self.get_page, version, p): p for p in todo}
                for future in as_completed(futures):
                    path = futures[future]
                    try:
                        loaded[path] = future.result()
                    except (FetchError, ValueError) as exc:
                        failures += 1
                        log.warning("Skipping %s: %s", path, exc)
            loaded = {p: loaded[p] for p in paths if p in loaded}  # drop pages no longer listed
            if not loaded:
                raise FetchError(f"Could not load any {version.source} {version.label} pages.")

            idx = SearchIndex()
            for page in loaded.values():
                idx.add_page(page, version.source, version.label)
            full_until = state.full_until if keep and state else now + self._max_age(version)
            if failures:
                # Back off 5, 10, 20... minutes while pages keep failing.
                retries = (state.retries if keep and state else 0) + 1
                retry_at = min(full_until, now + PARTIAL_INDEX_TTL * 2 ** (retries - 1))
            else:
                retries, retry_at = 0, full_until
            self._indexes[version] = _IndexState(idx, loaded, full_until, retry_at, retries)
            log.info(
                "Indexed %s %s: fetched %d of %d pages, %d failed, %d sections in %.1fs",
                version.source, version.label, len(todo) - failures, len(paths),
                failures, len(idx), time.time() - now,
            )
            return idx

    def search(
        self,
        query: str,
        source: str = "all",
        version: Optional[str] = None,
        limit: int = 8,
    ) -> SearchResult:
        """Search each requested source and version, skipping any that can't be loaded.

        An invalid version is the caller's mistake and raises ValueError. A source that
        can't be fetched is skipped and reported in SearchResult.skipped; FetchError is
        raised only when nothing could be searched.
        """
        if source not in ("all", *SOURCES):
            raise ValueError(f"Unknown source {source!r}. Use all, {', '.join(SOURCES)}.")
        targets: List[DocVersion] = []
        skipped: List[str] = []
        if source in ("all", "techdocs"):
            try:
                if (version or "").strip().lower() == "all":
                    targets.extend(self.catalog("techdocs").versions)
                else:
                    targets.append(self.resolve("techdocs", version))
            except FetchError as exc:
                skipped.append(f"{SOURCES['techdocs']}: {exc}")
        if source in ("all", "trainings"):
            try:
                targets.append(self.resolve("trainings", None))
            except FetchError as exc:
                skipped.append(f"{SOURCES['trainings']}: {exc}")

        hits: List[Hit] = []
        searched: List[DocVersion] = []
        for target in targets:
            try:
                idx = self.index(target)
            except FetchError as exc:
                skipped.append(f"{SOURCES[target.source]} {target.label}: {exc}")
                continue
            searched.append(target)
            hits.extend(idx.search(query, limit))
        if not searched:
            raise FetchError("No documentation could be searched. " + " ".join(skipped))
        hits.sort(key=lambda h: -h.score)
        return SearchResult(hits=hits[:limit], searched=searched, skipped=skipped)

    def start_prefetch(self) -> None:
        """Index the current tech docs and training material in the background."""

        def run() -> None:
            for source in SOURCES:
                try:
                    self.index(self.resolve(source, None))
                except Exception as exc:  # noqa: BLE001 - background warm-up only
                    log.warning("Prefetch of %s failed: %s", source, exc)

        threading.Thread(target=run, name="rtbrick-prefetch", daemon=True).start()
