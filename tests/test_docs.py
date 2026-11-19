import time

import pytest

from rtbrick_mcp_server.docs import (
    DocsLibrary,
    parse_current_version,
    parse_sitemap,
    select_versions,
)
from rtbrick_mcp_server.site import DOCS_ROOT, DiskCache, FetchError

from .conftest import TECH_SEGMENTS, FakeFetcher


def names(versions):
    return [v.name for v in versions]


def test_select_versions_keeps_newest_patch_of_five_release_lines():
    versions = select_versions("techdocs", TECH_SEGMENTS, "26.3.1", 5)
    assert names(versions) == ["26.3.1", "26.2.1.5", "26.1.1.1", "25.4.1.7", "25.3.1"]
    assert versions[0].is_current and versions[0].segment == "current"
    assert versions[1].segment == "26.2.1.5" and not versions[1].is_current


def test_select_versions_honours_limit_and_skips_numbered_copy_of_current():
    segments = ["current", "26.3.1", "26.2.1", "notes"]
    versions = select_versions("techdocs", segments, "26.3.1", 1)
    assert [(v.name, v.segment) for v in versions] == [("26.3.1", "current")]
    assert names(select_versions("techdocs", segments, "26.3.1", 5)) == ["26.3.1", "26.2.1"]


def test_select_versions_for_unnumbered_training():
    versions = select_versions("trainings", ["current"], "latest", 5)
    assert [(v.name, v.segment, v.is_current) for v in versions] == [("latest", "current", True)]
    assert versions[0].base_url == f"{DOCS_ROOT}trainings/current/"


def test_parse_sitemap_groups_html_pages_by_version(fetcher):
    pages = parse_sitemap(fetcher.responses[f"{DOCS_ROOT}sitemap-techdocs.xml"], "techdocs")
    assert sorted(pages) == sorted(TECH_SEGMENTS)
    assert pages["26.2.1.5"] == ["bgpug/bgp_intro.html", "evpn-vpws/evpn_vpws_config.html", "index.html"]


def test_parse_current_version(fetcher):
    html = fetcher.responses[f"{DOCS_ROOT}techdocs/current/index.html"]
    assert parse_current_version(html, "techdocs") == "26.3.1"
    assert parse_current_version(html, "trainings") is None


def test_resolve_versions(library):
    assert library.resolve("techdocs", None).label == "26.3.1 (current)"
    assert library.resolve("techdocs", "latest").name == "26.3.1"
    assert library.resolve("techdocs", "26.2").name == "26.2.1.5"
    assert library.resolve("techdocs", "26.2.1").name == "26.2.1.5"
    assert library.resolve("techdocs", "25.4.1.7").segment == "25.4.1.7"
    assert library.resolve("trainings", None).name == "latest"
    for unavailable in ("26.2.1.3", "25.2.1", "27"):
        with pytest.raises(ValueError, match="Available: 26.3.1 \\(current\\), 26.2.1.5"):
            library.resolve("techdocs", unavailable)
    with pytest.raises(ValueError, match="Unknown source"):
        library.resolve("videos", None)


def test_get_page_uses_the_version_url_and_caches(tmp_path, fetcher):
    lib = DocsLibrary(fetcher, DiskCache(tmp_path), workers=1)  # type: ignore[arg-type]
    v = lib.resolve("techdocs", "26.2")
    page = lib.get_page(v, "/evpn-vpws/evpn_vpws_config.html")
    assert page.url == f"{DOCS_ROOT}techdocs/26.2.1.5/evpn-vpws/evpn_vpws_config.html"
    assert "release 26.2.1.5" in page.sections[0].text
    calls = len(fetcher.calls)

    fresh = DocsLibrary(fetcher, DiskCache(tmp_path), workers=1)  # type: ignore[arg-type]
    assert fresh.get_page(v, "evpn-vpws/evpn_vpws_config.html") == page
    assert len(fetcher.calls) == calls  # served from the disk cache


def test_get_page_rejects_path_traversal(library):
    v = library.resolve("techdocs", None)
    with pytest.raises(ValueError, match="Invalid page path"):
        library.get_page(v, "../../trainings/current/index.html")


def test_stale_cache_is_used_when_site_is_down(tmp_path, fetcher):
    lib = DocsLibrary(fetcher, DiskCache(tmp_path), workers=1)  # type: ignore[arg-type]
    url = f"{DOCS_ROOT}techdocs/current/bgpug/bgp_intro.html"
    lib.get_page_by_url(url)
    offline = DocsLibrary(FakeFetcher({}), DiskCache(tmp_path), workers=1)  # type: ignore[arg-type]
    assert offline.get_page_by_url(url, max_age=0).title == "BGP Overview"


def test_search_defaults_to_current_techdocs_and_training(library):
    result = library.search("route reflector")
    assert [v.label for v in result.searched] == ["26.3.1 (current)", "latest"]
    urls = [h.url for h in result.hits]
    assert f"{DOCS_ROOT}techdocs/current/bgpug/bgp_intro.html#route-reflection" in urls
    assert f"{DOCS_ROOT}trainings/current/bgp/bgp_rr.html#module-introduction" in urls


def test_search_specific_version_and_all_versions(library):
    result = library.search("evpn instance", source="techdocs", version="25.4")
    assert {h.version for h in result.hits} == {"25.4.1.7"}
    result = library.search("evpn instance", source="techdocs", version="all", limit=25)
    assert [v.name for v in result.searched] == ["26.3.1", "26.2.1.5", "26.1.1.1", "25.4.1.7", "25.3.1"]
    assert {h.version for h in result.hits} == {v.label for v in result.searched}


def test_index_skips_pages_that_fail(fetcher):
    del fetcher.responses[f"{DOCS_ROOT}techdocs/current/bgpug/bgp_intro.html"]
    lib = DocsLibrary(fetcher, DiskCache(None), workers=2)  # type: ignore[arg-type]
    hits = lib.search("evpn", source="techdocs").hits
    assert hits and all("bgp_intro" not in h.url for h in hits)


def test_search_skips_a_source_that_is_down(fetcher):
    del fetcher.responses[f"{DOCS_ROOT}sitemap-trainings.xml"]
    lib = DocsLibrary(fetcher, DiskCache(None), workers=2)  # type: ignore[arg-type]
    result = lib.search("route reflector")
    assert [v.source for v in result.searched] == ["techdocs"]
    assert result.hits and all(h.source == "techdocs" for h in result.hits)
    assert len(result.skipped) == 1 and result.skipped[0].startswith("Training: HTTP 404")


def test_search_fails_only_when_nothing_can_be_searched():
    lib = DocsLibrary(FakeFetcher({}), DiskCache(None))  # type: ignore[arg-type]
    with pytest.raises(FetchError, match="No documentation could be searched"):
        lib.search("bgp")


def test_invalid_version_is_still_an_error_with_source_all(library):
    with pytest.raises(ValueError, match="not available"):
        library.search("bgp", version="24.1")


def test_invalid_sitemap_is_not_cached_and_stale_copy_is_used(tmp_path, fetcher):
    sitemap_url = f"{DOCS_ROOT}sitemap-techdocs.xml"
    good = fetcher.responses[sitemap_url]

    # No cached copy yet: a maintenance page is an error, and must not be cached.
    fetcher.responses[sitemap_url] = "<html><body>Down for maintenance</body></html>"
    lib = DocsLibrary(fetcher, DiskCache(tmp_path), workers=1)  # type: ignore[arg-type]
    with pytest.raises(FetchError, match="not valid XML|lists no pages"):
        lib.catalog("techdocs")
    fetcher.responses[sitemap_url] = good
    lib = DocsLibrary(fetcher, DiskCache(tmp_path), workers=1)  # type: ignore[arg-type]
    assert lib.catalog("techdocs").versions[0].name == "26.3.1"

    # With a good copy cached, a later bad response falls back to it.
    fetcher.responses[sitemap_url] = "<?xml version='1.0'?><urlset></urlset>"
    lib = DocsLibrary(fetcher, DiskCache(tmp_path), workers=1, ttl_seconds=0)  # type: ignore[arg-type]
    assert lib.catalog("techdocs").versions[0].name == "26.3.1"


def test_partial_index_is_retried_soon(fetcher, monkeypatch):
    url = f"{DOCS_ROOT}techdocs/current/bgpug/bgp_intro.html"
    page_html = fetcher.responses.pop(url)
    lib = DocsLibrary(fetcher, DiskCache(None), workers=2)  # type: ignore[arg-type]
    v = lib.resolve("techdocs", None)
    assert not lib.index(v).search("reflector")

    fetcher.responses[url] = page_html
    assert not lib.index(v).search("reflector")  # still within the retry delay
    later = time.time() + 6 * 60
    monkeypatch.setattr(time, "time", lambda: later)
    assert lib.index(v).search("reflector")[0].url == url + "#route-reflection"


def test_retry_fetches_only_failed_pages_and_backs_off(fetcher, monkeypatch):
    broken = f"{DOCS_ROOT}techdocs/current/bgpug/bgp_intro.html"
    page_html = fetcher.responses.pop(broken)
    lib = DocsLibrary(fetcher, DiskCache(None), workers=2)  # type: ignore[arg-type]
    v = lib.resolve("techdocs", None)
    start = time.time()
    clock = {"now": start}
    monkeypatch.setattr(time, "time", lambda: clock["now"])

    def fetched_pages():
        return [u for u in fetcher.calls if "/techdocs/current/" in u and "index.html" not in u]

    lib.index(v)
    assert sorted(fetched_pages()) == sorted([broken, broken.replace("bgpug/bgp_intro", "evpn-vpws/evpn_vpws_config")])

    # First retry after 5 minutes: only the failed page is fetched, and it fails again.
    fetcher.calls.clear()
    clock["now"] = start + 5 * 60 + 1
    lib.index(v)
    assert fetched_pages() == [broken]

    # The next retry waits 10 minutes, not 5.
    fetcher.calls.clear()
    clock["now"] = start + 11 * 60
    lib.index(v)
    assert fetched_pages() == []
    fetcher.responses[broken] = page_html
    clock["now"] = start + 15 * 60 + 2
    assert lib.index(v).search("reflector")[0].url == broken + "#route-reflection"
    assert fetched_pages() == [broken]


def test_non_html_pages_are_returned_verbatim(fetcher, library):
    body = "name: rbfs\n  indent: kept\n"
    fetcher.responses["https://www.rtbrick.com/files/notes.yaml"] = body
    page = library.get_page_by_url("https://www.rtbrick.com/files/notes.yaml")
    assert page.sections[0].text == body


def test_unreachable_sitemap_is_an_error():
    lib = DocsLibrary(FakeFetcher({}), DiskCache(None))  # type: ignore[arg-type]
    with pytest.raises(FetchError, match="HTTP 404"):
        lib.catalog("techdocs")
