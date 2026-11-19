# RTBrick MCP Server

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Python%20SDK-green)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that lets Claude and
other MCP clients search and read RTBrick's RBFS documentation — no API key required.

| Source | Index page |
|--------|------------|
| Technical Documentation | https://www.rtbrick.com/docs/techdocs/current/index.html |
| Training | https://www.rtbrick.com/docs/trainings/current/index.html |
| Website | https://www.rtbrick.com |

---

## What it does

- **Covers every page.** Pages are discovered from the site's sitemaps
  (`sitemap-techdocs.xml`, `sitemap-trainings.xml`), so new guides appear without code changes.
- **Recent versions.** The tech docs publish every patch release (26.2.1, 26.2.1.1 … 26.2.1.5).
  The server offers the **newest patch of each of the 5 most recent release lines**, e.g.
  `26.3.1 (current)`, `26.2.1.5`, `26.1.1.1`, `25.4.1.7`. Training material has one version.
- **Section-level search.** BM25 ranking over page sections; every word of the query counts,
  so "route reflector" or "evpn vpws configuration" find the right sections, and each result
  links straight to its `#section`.
- **Clean text.** Only the article is extracted; CLI examples stay in code blocks with their
  indentation, and attribute tables keep one row per line.
- **Fast after the first run.** Pages are cached on disk. At startup the current tech docs and
  training material are indexed in the background (about 15 s on first run); other versions are
  indexed on first use (about 10 s each).
- **Locked down.** Only `rtbrick.com`, `www.rtbrick.com` and `documents.rtbrick.com` over HTTPS,
  checked again on every redirect; responses are capped at 10 MB; all tools are read-only.

## Tools

| Tool | Purpose |
|------|---------|
| `search_docs(query, source="all", version=None, max_results=8)` | Search tech docs and/or training. `version` takes a release line (`"26.2"`), an exact version (`"26.2.1.5"`), `"all"`, or nothing for current. |
| `get_doc_page(page, source="techdocs", version=None, section=None, offset=0, max_chars=20000)` | Read a page by search-result link or by path (`"evpn-vpws/evpn_vpws_config.html"`). A `#fragment` or `section` returns just that section and its subsections. Long pages are paginated. |
| `list_doc_versions()` | The versions on offer and their page counts. |
| `list_doc_pages(source="techdocs", version=None, contains=None)` | Browse pages grouped by guide, optionally filtered (`contains="evpn"`). |
| `fetch_rtbrick_page(url, offset=0, max_chars=20000)` | Read any other page on www.rtbrick.com. |

---

## Installation

Requires Python 3.10 or later.

### Run with uvx (no install step)

```bash
uvx --from git+https://github.com/rtbrick/rtb-mcp rtbrick-mcp-server
```

### From source

```bash
git clone https://github.com/rtbrick/rtb-mcp.git
cd rtb-mcp
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
rtbrick-mcp-server --help
```

## Client configuration

### Claude Code

```bash
claude mcp add rtbrick -- uvx --from git+https://github.com/rtbrick/rtb-mcp rtbrick-mcp-server
```

### Claude Desktop

Edit `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`, Linux: `~/.config/Claude/`):

```json
{
  "mcpServers": {
    "rtbrick": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/rtbrick/rtb-mcp", "rtbrick-mcp-server"]
    }
  }
}
```

If you installed from source, use `"command": "/path/to/rtb-mcp/.venv/bin/rtbrick-mcp-server"`
with no `args`. Restart Claude Desktop afterwards.

### As a shared HTTP server

```bash
rtbrick-mcp-server --transport streamable-http --host 0.0.0.0 --port 8000
```

Clients connect to `http://<host>:8000/mcp`.

---

## Configuration

All settings are optional environment variables.

| Variable | Default | Meaning |
|----------|---------|---------|
| `RTBRICK_MCP_MAX_VERSIONS` | `5` | Number of recent release lines to offer (newest patch of each). |
| `RTBRICK_MCP_CACHE_DIR` | `~/.cache/rtbrick-mcp` | Page cache location; `off` disables it. |
| `RTBRICK_MCP_CACHE_TTL_HOURS` | `24` | Freshness of the current release's pages and the sitemaps. Numbered releases are kept for 30 days. |
| `RTBRICK_MCP_PREFETCH` | `1` | `0` skips background indexing at startup (same as `--no-prefetch`). |
| `RTBRICK_MCP_WORKERS` | `8` | Parallel downloads while indexing. |
| `RTBRICK_MCP_LOG_LEVEL` | `INFO` | Log level; logs go to stderr. |
| `RTBRICK_MCP_TRANSPORT`, `RTBRICK_MCP_HOST`, `RTBRICK_MCP_PORT` | `stdio`, `127.0.0.1`, `8000` | Defaults for the matching command-line options. |

If rtbrick.com is unreachable, the server answers from cached pages even when they are stale.

---

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

The tests run offline against a small fake site shaped like the real one. Try the server
interactively with the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector rtbrick-mcp-server
```

Code layout:

| Module | Responsibility |
|--------|----------------|
| `rtbrick_mcp_server/server.py` | MCP tools (SDK 2.x `MCPServer`) and command-line entry point |
| `rtbrick_mcp_server/docs.py` | Sitemaps, version selection, page retrieval, indexing |
| `rtbrick_mcp_server/extract.py` | HTML → sections (title, anchors, code blocks, tables) |
| `rtbrick_mcp_server/search.py` | BM25 section search |
| `rtbrick_mcp_server/site.py` | Host allowlist, HTTP fetching, disk cache |

---

## License

MIT License — Copyright (c) 2025-2026 Pravin Bhandarkar, RTBrick Inc.
See [LICENSE](LICENSE) for the full text.

Issues and pull requests are welcome on [GitHub](https://github.com/rtbrick/rtb-mcp).
