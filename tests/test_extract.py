from rtbrick_mcp_server.extract import Page, extract_page

from .conftest import antora_page, evpn_config

URL = "https://www.rtbrick.com/docs/techdocs/current/evpn-vpws/evpn_vpws_config.html"


def _page() -> Page:
    title, body = evpn_config("26.3.1")
    return extract_page(antora_page("techdocs", "26.3.1", title, body), URL)


def test_title_and_section_anchors():
    page = _page()
    assert page.title == "EVPN VPWS Configuration"
    assert [s.anchor for s in page.sections] == [
        "",
        "configuration-hierarchy",
        "configuration-syntax-and-commands",
        "evpn-instance-configuration",
        "bgp-configuration",
    ]
    assert [s.level for s in page.sections][1:] == [2, 2, 3, 3]


def test_only_article_content_is_kept():
    text = _page().to_markdown()
    for chrome in ("NAVTEXT", "HEADERTEXT", "FOOTERTEXT", "SCRIPTTEXT"):
        assert chrome not in text
    assert "EVPN VPWS reference for release 26.3.1." in text


def test_code_blocks_keep_indentation_and_entities_are_decoded():
    page = _page()
    section = page.section_slice("evpn-instance-configuration")[0]
    assert "```\nset instance evpn-vpws-vrf1\n  protocol bgp\n    route-target 65000:1\n```" in section.text
    assert "instance & protocol" in page.sections[1].text


def test_table_rows_are_pipe_separated():
    section = _page().section_slice("evpn-instance-configuration")[0]
    assert (
        "Attribute | Description\n`route-distinguisher` | Route distinguisher for the instance."
        in section.text
    )


def test_section_slice_includes_subsections_and_matches_headings():
    page = _page()
    parent = page.section_slice("configuration-syntax-and-commands")
    assert [s.anchor for s in parent] == [
        "configuration-syntax-and-commands",
        "evpn-instance-configuration",
        "bgp-configuration",
    ]
    assert [s.anchor for s in page.section_slice("BGP configuration")] == ["bgp-configuration"]
    assert page.section_slice("#configuration-hierarchy")[0].heading == "Configuration Hierarchy"
    assert page.section_slice("no such thing") == []


def test_section_url_and_round_trip():
    page = _page()
    assert page.section_url(page.sections[1]) == URL + "#configuration-hierarchy"
    assert Page.from_dict(page.to_dict()) == page


def test_pages_without_article_fall_back_to_body():
    html = (
        "<html><head><title>Products</title></head><body><header>MENU</header>"
        "<h1>RBFS Products</h1><p>Disaggregated BNG.</p><footer>LEGAL</footer></body></html>"
    )
    page = extract_page(html, "https://www.rtbrick.com/products")
    assert page.title == "RBFS Products"
    text = page.to_markdown()
    assert "Disaggregated BNG." in text
    assert "MENU" not in text and "LEGAL" not in text
