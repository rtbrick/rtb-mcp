from rtbrick_mcp_server.extract import Page, Section
from rtbrick_mcp_server.search import SearchIndex, tokenize


def _index() -> SearchIndex:
    idx = SearchIndex()
    idx.add_page(
        Page("https://x/bgp.html", "BGP Overview", [
            Section("route-reflection", "Route Reflection", 2,
                    "A route reflector reduces the number of iBGP sessions."),
            Section("timers", "Timers", 2, "Keepalive and hold timers."),
        ]),
        "techdocs", "26.3.1",
    )
    idx.add_page(
        Page("https://x/evpn.html", "EVPN VPWS Configuration", [
            Section("instance", "EVPN Instance Configuration", 3,
                    "```\nset instance evpn-vpws-vrf1\n```"),
        ]),
        "techdocs", "26.3.1",
    )
    idx.add_page(
        Page("https://x/static.html", "Static Routes", [
            Section("route", "Static Route", 2, "A static route to a next hop."),
        ]),
        "techdocs", "26.3.1",
    )
    return idx


def test_tokenize_splits_compounds_and_stems_plurals():
    assert tokenize("EVPN-VPWS Reflectors policies") == [
        "evpn-vpw", "evpn", "vpw", "reflector", "policy",
    ]
    assert "the" not in tokenize("the route")


def test_multi_word_query_does_not_need_exact_phrase():
    hits = _index().search("reflector route")
    assert hits[0].url == "https://x/bgp.html#route-reflection"


def test_section_matching_all_terms_ranks_above_partial_match():
    hits = _index().search("route reflectors")
    assert [h.url for h in hits][:2] == [
        "https://x/bgp.html#route-reflection",
        "https://x/static.html#route",
    ]


def test_compound_terms_match_their_parts():
    hits = _index().search("vpws instance")
    assert hits[0].url == "https://x/evpn.html#instance"
    assert "set instance evpn-vpws-vrf1" in hits[0].snippet
    assert "```" not in hits[0].snippet


def test_no_match_and_empty_query():
    idx = _index()
    assert idx.search("multicast") == []
    assert idx.search("the a of") == []
