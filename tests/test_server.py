"""MCP-level tests. They need the mcp SDK 2.x (Python 3.10+) and are skipped without it."""

import asyncio

import pytest

pytest.importorskip("mcp")

from rtbrick_mcp_server import server  # noqa: E402
from rtbrick_mcp_server.site import DOCS_ROOT  # noqa: E402


@pytest.fixture(autouse=True)
def fake_library(library):
    server.set_library(library)
    yield
    server.set_library(None)


def call(name, **arguments):
    result = asyncio.run(server.mcp.call_tool(name, arguments))
    assert not result.is_error
    return result.content[0].text


def test_tools_are_listed_as_read_only():
    tools = asyncio.run(server.mcp.list_tools())
    assert sorted(t.name for t in tools) == [
        "fetch_rtbrick_page", "get_doc_page", "list_doc_pages", "list_doc_versions", "search_docs",
    ]
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)


def test_search_docs_returns_section_links():
    text = call("search_docs", query="route reflector")
    assert "Technical Documentation 26.3.1 (current), Training latest" in text
    assert f"{DOCS_ROOT}techdocs/current/bgpug/bgp_intro.html#route-reflection" in text


def test_get_doc_page_by_link_with_fragment():
    url = f"{DOCS_ROOT}techdocs/current/evpn-vpws/evpn_vpws_config.html#bgp-configuration"
    text = call("get_doc_page", page=url)
    assert text.startswith(f"Source: {url}\nVersion: Technical Documentation 26.3.1 (current)")
    assert "l2vpn-evpn" in text and "Configuration Hierarchy" not in text


def test_get_doc_page_by_path_and_version():
    text = call("get_doc_page", page="evpn-vpws/evpn_vpws_config.html", version="26.1")
    assert f"Source: {DOCS_ROOT}techdocs/26.1.1.1/evpn-vpws/evpn_vpws_config.html" in text
    assert "Version: Technical Documentation 26.1.1.1" in text
    assert "EVPN VPWS reference for release 26.1.1.1." in text


def test_pagination():
    text = "x" * 2500
    first = server._paginate(text, 0, 1000)
    assert first.startswith("x" * 1000) and "Call again with offset=1000" in first
    last = server._paginate(text, 2000, 1000)
    assert "End of page: characters 2000-2500 of 2500" in last
    with pytest.raises(Exception, match="past the end"):
        server._paginate(text, 3000, 1000)


def test_list_doc_versions_and_pages():
    text = call("list_doc_versions")
    assert "- 26.2.1.5: https://www.rtbrick.com/docs/techdocs/26.2.1.5/index.html (3 pages)" in text
    text = call("list_doc_pages", contains="evpn")
    assert "evpn-vpws/: evpn_vpws_config.html" in text


def test_errors_are_tool_errors():
    with pytest.raises(Exception, match="not allowed"):
        call("fetch_rtbrick_page", url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    with pytest.raises(Exception, match="not available"):
        call("search_docs", query="bgp", version="24.1")
