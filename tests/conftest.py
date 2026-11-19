"""Offline fixtures: a small fake rtbrick.com shaped like the real Antora docs site."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pytest

from rtbrick_mcp_server.docs import DocsLibrary
from rtbrick_mcp_server.site import DOCS_ROOT, DiskCache, FetchError, validate_url

# Segments as they appear in sitemap-techdocs.xml; "current" is 26.3.1.
TECH_SEGMENTS = ["current", "26.2.1", "26.2.1.5", "26.1.1.1", "25.4.1", "25.4.1.7", "25.3.1", "25.2.1"]


def antora_page(source: str, version: str, title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>{title} :: Resources</title><script>var x = "SCRIPTTEXT";</script></head>
<body>
<header class="header"><nav>HEADERTEXT</nav></header>
<div class="nav-container" data-component="{source}" data-version="{version}">
  <nav class="nav-menu">NAVTEXT</nav>
</div>
<main class="article">
<article class="doc">
<h1 class="page">{title}</h1>
{body}
</article>
</main>
<footer>FOOTERTEXT</footer>
</body></html>"""


def sect(level: int, anchor: str, heading: str, body: str) -> str:
    return (
        f'<div class="sect{level - 1}"><h{level} id="{anchor}"><a class="anchor" '
        f'href="#{anchor}"></a>{heading}</h{level}><div class="sectionbody">{body}</div></div>'
    )


def evpn_config(version: str) -> Tuple[str, str]:
    body = (
        f'<div id="preamble"><p>EVPN VPWS reference for release {version}.</p></div>'
        + sect(2, "configuration-hierarchy", "Configuration Hierarchy",
               "<p>The hierarchy shows the instance &amp; protocol levels.</p>")
        + sect(2, "configuration-syntax-and-commands", "Configuration Syntax and Commands",
               "<p>Commands follow.</p>"
               + sect(3, "evpn-instance-configuration", "EVPN Instance Configuration",
                      '<table class="tableblock"><tr><th>Attribute</th><th>Description</th></tr>'
                      "<tr><td><p><code>route-distinguisher</code></p></td>"
                      "<td><p>Route distinguisher for the instance.</p></td></tr></table>"
                      '<div class="listingblock"><pre>set instance evpn-vpws-vrf1\n'
                      "  protocol bgp\n    route-target 65000:1</pre></div>")
               + sect(3, "bgp-configuration", "BGP Configuration",
                      "<p>Enable the l2vpn-evpn address family on the BGP peer group.</p>"))
    )
    return "EVPN VPWS Configuration", body


def bgp_intro(version: str) -> Tuple[str, str]:
    body = sect(2, "route-reflection", "Route Reflection",
                "<p>A route reflector reduces the number of iBGP sessions in a cluster.</p>"
                "<ul><li>Clients peer only with the reflector.</li><li>Uses cluster IDs.</li></ul>")
    body += sect(2, "timers", "Timers", "<p>Keepalive and hold timers are configurable.</p>")
    return "BGP Overview", body


def training_rr(_: str) -> Tuple[str, str]:
    body = sect(2, "module-introduction", "Module Introduction",
                "<p>This module covers BGP route reflectors in the lab.</p>"
                '<div class="listingblock"><pre class="highlightjs"><code class="language-cli">'
                "cfg&gt; show bgp rib-out ipv4 unicast</code></pre></div>")
    return "BGP Route Reflectors", body


TECH_PAGES = {"index.html": None, "evpn-vpws/evpn_vpws_config.html": evpn_config,
              "bgpug/bgp_intro.html": bgp_intro}
TRAINING_PAGES = {"index.html": None, "bgp/bgp_rr.html": training_rr}


def sitemap(urls: List[str]) -> str:
    entries = "".join(f"<url><loc>{u}</loc><lastmod>2026-11-01</lastmod></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'
    )


def build_site() -> Dict[str, str]:
    site: Dict[str, str] = {}
    tech_urls: List[str] = []
    for segment in TECH_SEGMENTS:
        version = "26.3.1" if segment == "current" else segment
        for path, builder in TECH_PAGES.items():
            url = f"{DOCS_ROOT}techdocs/{segment}/{path}"
            tech_urls.append(url)
            title, body = builder(version) if builder else ("Technical Documentation", "<p>Index</p>")
            site[url] = antora_page("techdocs", version, title, body)
        tech_urls.append(f"{DOCS_ROOT}techdocs/{segment}/rbfs-user-guides.pdf")
    train_urls = []
    for path, builder in TRAINING_PAGES.items():
        url = f"{DOCS_ROOT}trainings/current/{path}"
        train_urls.append(url)
        title, body = builder("latest") if builder else ("Training", "<p>Index</p>")
        site[url] = antora_page("trainings", "latest", title, body)
    site[f"{DOCS_ROOT}sitemap-techdocs.xml"] = sitemap(tech_urls)
    site[f"{DOCS_ROOT}sitemap-trainings.xml"] = sitemap(train_urls)
    site["https://www.rtbrick.com/products"] = (
        "<html><head><title>Products</title></head><body><header>MENU</header>"
        "<h1>RBFS Products</h1><p>Disaggregated BNG and routing.</p><footer>LEGAL</footer></body></html>"
    )
    return site


class FakeFetcher:
    def __init__(self, responses: Dict[str, str]) -> None:
        self.responses = responses
        self.calls: List[str] = []

    def get(self, url: str) -> str:
        url = validate_url(url)
        self.calls.append(url)
        if url not in self.responses:
            raise FetchError(f"HTTP 404 for {url}")
        return self.responses[url]


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher(build_site())


@pytest.fixture
def library(fetcher: FakeFetcher) -> DocsLibrary:
    return DocsLibrary(fetcher, DiskCache(None), workers=2)  # type: ignore[arg-type]
