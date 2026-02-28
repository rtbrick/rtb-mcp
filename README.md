# RTBrick MCP Server

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2024--11--05-green)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-stable-brightgreen)](https://github.com/rtbrick/rtbrick-mcp-server)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that gives AI assistants direct access to RTBrick's website, technical documentation, and YouTube training videos — with no API key required.

---

## Overview

RTBrick makes disaggregated routing software for telcos. This MCP server lets Claude (and any MCP-compatible AI) query RTBrick's publicly available resources in real time:

| Source | URL |
|--------|-----|
| RTBrick Website | https://www.rtbrick.com |
| Technical Docs | https://documents.rtbrick.com/techdocs/current/index.html |
| Training Videos | https://www.youtube.com/@rtbrick7767 |

All requests are validated against a strict domain allowlist — only `rtbrick.com`, `documents.rtbrick.com`, and `www.youtube.com` are reachable.

---

## Features

- **Real-time access** — content is fetched live and cached for one hour
- **Zero API keys** — works out of the box with no credentials
- **Domain allowlist** — only RTBrick and YouTube domains are accessible
- **Robust HTTP client** — automatic retries with exponential backoff, connection pooling
- **Thread-safe TTL cache** — avoids redundant network requests within a session
- **Keyword search** — relevance-scored search across all 23 tech-doc pages
- **YouTube oEmbed** — fetches video/playlist metadata without the YouTube Data API

---

## Available Tools

| Tool | Description |
|------|-------------|
| `fetch_rtbrick_page` | Fetch any page from an allowed RTBrick or YouTube domain by URL |
| `get_rtbrick_website` | Fetch the RTBrick main website landing page |
| `get_tech_docs_index` | Fetch the RTBrick technical documentation index |
| `search_tech_docs` | Keyword search across all 23 tech-doc pages with ranked results |
| `list_tech_docs` | List all available technical documentation pages and their URLs |
| `get_rtbrick_videos` | Get RTBrick's YouTube training-video playlist metadata |
| `get_youtube_video_info` | Fetch oEmbed metadata for a specific RTBrick YouTube video URL |

---

## Requirements

- Python 3.9 or later
- `requests` library (and `urllib3`)

---

## Installation

### Option 1 — pip (recommended)

```bash
pip install rtbrick-mcp-server
```

### Option 2 — From source

```bash
git clone https://github.com/rtbrick/rtbrick-mcp-server.git
cd rtbrick-mcp-server
pip install -r requirements.txt
```

### Option 3 — pipx (isolated install)

```bash
pipx install rtbrick-mcp-server
```

---

## Quick Start

Run the server directly to verify it starts:

```bash
python mcpserver_opt_1.py
```

You should see a log line like:
```
2025-01-01 00:00:00  INFO      __init__:NN  RTBrick MCP Server ready — 23 tech-doc paths configured
```

The server reads JSON-RPC 2.0 from **stdin** and writes responses to **stdout**, which is the standard MCP stdio transport.

---

## Claude Desktop Configuration

Add the following to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

### If installed via pip

```json
{
  "mcpServers": {
    "rtbrick": {
      "command": "rtb-mcp"
    }
  }
}
```

### If running from source

```json
{
  "mcpServers": {
    "rtbrick": {
      "command": "python3",
      "args": ["/absolute/path/to/rtb-mcp/mcpserver_opt_1.py"]
    }
  }
}
```

### With a custom config file

```json
{
  "mcpServers": {
    "rtbrick": {
      "command": "python3",
      "args": ["/absolute/path/to/rtb-mcp/mcpserver_opt_1.py"],
      "env": {
        "CONFIG_PATH": "/path/to/your/config.json"
      }
    }
  }
}
```

After editing, **restart Claude Desktop**.

---

## Optional `config.json`

The server works with no config file. If you want to customise the list of tech-doc pages or cache settings, create a `config.json`:

```json
{
"name": "rtbrick-website",
  "description": "RTBrick website content crawled from https://documents.rtbrick.com",
  "base_url": "https://documents.rtbrick.com",
  "doc_paths": [
    "index-1.html",
    "index.html",
    "techdocs/25.4.1.2/cgnat-appliance/cgnat_appliance_config_cmds.html",
    "techdocs/25.4.1.2/ctrld/02_switch_mgmt_rbfs_api_fundamentals.html",
    "techdocs/25.4.1.2/index.html",
    "techdocs/25.4.1.2/l2vpn/l2vpn_intro.html",
    "techdocs/25.4.1.2/l2xug/l2x_config.html",
    "techdocs/25.4.1.2/ngaccess/access_config_l2tp_pool.html",
    "techdocs/25.4.1.2/ntpug/ntp_intro.html",
    "techdocs/25.4.1.2/ntpug/ntp_operation_cmds.html",
    "techdocs/25.4.1.2/platform/rbfs_ufispace_s9510_28dc.html",
    "techdocs/25.4.1.2/policyug/policy_operations.html",
    "techdocs/25.4.1.2/radiusservices/radius_control.html",
    "techdocs/25.4.1.2/refdesign-cgnat/cbng_cgnat_refdesign_overview.html",
    "techdocs/25.4.1.2/refdesign-ha/cbngipoe-rd-config.html",
    "techdocs/25.4.1.2/refdesign/cbngipoe_refdesign_config_protocols.html",
    "techdocs/25.4.1.2/ribug/rib-operational-commands.html",
    "techdocs/25.4.1.2/routeleak/routeleak_config.html",
    "techdocs/25.4.1.2/tsdb/tsdb_intro.html",
}
```

Config file search order:
1. `$CONFIG_PATH` environment variable
2. `config.json` in the current working directory
3. `config.json` next to the script
4. `~/.config/rtb-doc-mcp-server/config.json`

---

## Tool Reference

### `fetch_rtbrick_page`

Fetch content from any URL on an allowed RTBrick or YouTube domain.

```
Input:  { "url": "https://www.rtbrick.com/products" }
Output: Plain-text content of the page
```

### `get_rtbrick_website`

Fetches https://www.rtbrick.com and returns its text content.

```
Input:  {}
Output: RTBrick website landing page text
```

### `get_tech_docs_index`

Fetches the RTBrick technical documentation index.

```
Input:  {}
Output: Tech-docs index page text
```

### `search_tech_docs`

Searches across all 23 configured tech-doc pages and returns ranked results with context snippets.

```
Input:  { "query": "BGP route reflector" }
Output: Ranked list of matching sections with surrounding context
```

### `list_tech_docs`

Returns all configured documentation page paths and their full URLs.

```
Input:  {}
Output: Numbered list of doc paths, with ✓ marking cached entries
```

### `get_rtbrick_videos`

Returns metadata for the RTBrick YouTube training-video playlist using the YouTube oEmbed API.

```
Input:  {}
Output: Title, channel name, channel URL, thumbnail URL, and playlist link
```

### `get_youtube_video_info`

Returns oEmbed metadata for a specific RTBrick YouTube video URL.

```
Input:  { "url": "https://www.youtube.com/watch?v=1MhY-1M6Me8" }
Output: Title, channel, thumbnail URL, dimensions
```

---

## Technical Documentation Coverage

The following RTBrick RBFS topic areas are covered out of the box:

| Category | Pages |
|----------|-------|
| BGP | bgp_intro |
| IS-IS | isis_intro |
| OSPF | ospf_intro |
| Interfaces | interfaces_intro, interfaces_config |
| LAG | lag_overview, lag_config |
| L3 VPN | l3vpn_intro |
| EVPN-VPWS | evpn_vpws_intro |
| L2 Cross-connect | l2x_intro |
| HQoS | hqos_intro |
| ACL | acl_intro |
| ARP/ND | ipneighbor_config |
| LLDP | lldp_intro |
| Logging | logging_intro |
| Resource Monitor | resmon_intro, resmon_config_cmds, resmon_operation_cmds |
| Controller (ctrld) | ctrld_overview |
| TSDB | tsdb_intro |
| NG Access | access_intro |
| Tools | manual_installation |
| Index | index |

---

## Security

- Only `https://` URLs are accepted — plain `http://` is rejected
- Requests are constrained to a strict domain allowlist
- No credentials, tokens, or user data are transmitted
- All content is fetched read-only

---

## License

MIT License — Copyright (c) 2025-2026 Pravin Bhandarkar, RTBrick Inc.
See [LICENSE](LICENSE) for full text.

---

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/rtbrick/rtbrick-mcp-server).

---

## Related

- [RTBrick Website](https://www.rtbrick.com)
- [RTBrick Technical Documentation](https://documents.rtbrick.com/techdocs/current/index.html)
- [RTBrick YouTube Channel](https://www.youtube.com/@rtbrick7767)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Desktop](https://claude.ai/download)
