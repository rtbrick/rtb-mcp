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
  "base_url": "https://documents.rtbrick.com",
  "doc_paths": [
    "techdocs/current/aclug/acl_config.html",
    "techdocs/current/aclug/acl_intro.html",
    "techdocs/current/aclug/acl_operation.html",
    "techdocs/current/api/rbfs-apis-1.html",
    "techdocs/current/api/rbfs-apis.html",
    "techdocs/current/arpndug/ipneighbor_config.html",
    "techdocs/current/arpndug/ipneighbor_intro.html",
    "techdocs/current/arpndug/ipneighbor_operation.html",
    "techdocs/current/bdsug/bds_operational_cmds.html",
    "techdocs/current/bdsug/bds_overview.html",
    "techdocs/current/bfdug/bfd-config.html",
    "techdocs/current/bfdug/bfd-operation.html",
    "techdocs/current/bfdug/bfd-overview.html",
    "techdocs/current/bgpflowspec/flowspec_config_cmds.html",
    "techdocs/current/bgpflowspec/flowspec_intro.html",
    "techdocs/current/bgpflowspec/flowspec_operation_cmds.html",
    "techdocs/current/bgprpki/bgp-rpki-config.html",
    "techdocs/current/bgprpki/bgp-rpki-operation.html",
    "techdocs/current/bgprpki/bgp-rpki-overview.html",
    "techdocs/current/bgpug/bgp_config_cmds.html",
    "techdocs/current/bgpug/bgp_intro.html",
    "techdocs/current/bgpug/bgp_operation_cmds.html",
    "techdocs/current/cfm/cfm_config.html",
    "techdocs/current/cfm/cfm_intro.html",
    "techdocs/current/cfm/cfm_operation_cmds.html",
    "techdocs/current/cgnat-appliance/cgnat_appliance_config_cmds.html",
    "techdocs/current/cgnat-appliance/cgnat_appliance_intro.html",
    "techdocs/current/cgnat-appliance/cgnat_appliance_operation_cmds.html",
    "techdocs/current/cgnat/rbfs_cgnat_config_cmds.html",
    "techdocs/current/cgnat/rbfs_cgnat_intro.html",
    "techdocs/current/cgnat/rbfs_cgnat_operation_cmds.html",
    "techdocs/current/cliug/rbfs_cli_userguide.html",
    "techdocs/current/clocksync/clock_sync_config.html",
    "techdocs/current/clocksync/clock_sync_intro.html",
    "techdocs/current/clocksync/clock_sync_operation.html",
    "techdocs/current/ctrld/01_switch_mgmt_api.html",
    "techdocs/current/ctrld/02_switch_mgmt_rbfs_api_fundamentals.html",
    "techdocs/current/ctrld/03_switch_mgmt_configuration.html",
    "techdocs/current/ctrld/04_business_events.html",
    "techdocs/current/ctrld/05_switch_mgmt_related_documentation.html",
    "techdocs/current/ctrld/06_appendix_examples.html",
    "techdocs/current/ctrld/ctrld_overview.html",
    "techdocs/current/dhcpug/dhcp_config_dhcp_relay.html",
    "techdocs/current/dhcpug/dhcp_intro.html",
    "techdocs/current/dhcpug/dhcp_operational_cmds.html",
    "techdocs/current/eol/eol_policy.html",
    "techdocs/current/evpn-vpws/evpn_vpws_config.html",
    "techdocs/current/evpn-vpws/evpn_vpws_intro.html",
    "techdocs/current/evpn-vpws/evpn_vpws_operation.html",
    "techdocs/current/hqos/hqos_config_cmds.html",
    "techdocs/current/hqos/hqos_intro.html",
    "techdocs/current/hqos/hqos_runnig_config.html",
    "techdocs/current/hqos/hqos_show_cmds.html",
    "techdocs/current/http-redirect/http-redirect-config.html",
    "techdocs/current/http-redirect/http-redirect-overview.html",
    "techdocs/current/igmpug/igmp_config.html",
    "techdocs/current/igmpug/igmp_intro.html",
    "techdocs/current/igmpug/igmp_operation.html",
    "techdocs/current/inbandmgmt/inbandmgmt_config.html",
    "techdocs/current/inbandmgmt/inbandmgmt_operation.html",
    "techdocs/current/inbandmgmt/inbandmgmt_overview.html",
    "techdocs/current/index.html",
    "techdocs/current/interfacesug/interfaces_config.html",
    "techdocs/current/interfacesug/interfaces_intro.html",
    "techdocs/current/interfacesug/interfaces_operation.html",
    "techdocs/current/ipmiug/ipmi_config_cmds.html",
    "techdocs/current/ipmiug/ipmi_intro.html",
    "techdocs/current/ipmiug/ipmi_operation_cmds.html",
    "techdocs/current/isisug/isis_config.html",
    "techdocs/current/isisug/isis_intro.html",
    "techdocs/current/isisug/isis_operation.html",
    "techdocs/current/l2bsaug/l2bsa_api.html",
    "techdocs/current/l2bsaug/l2bsa_config.html",
    "techdocs/current/l2bsaug/l2bsa_introduction.html",
    "techdocs/current/l2bsaug/l2bsa_operation.html",
    "techdocs/current/l2vpn/l2vpn_config.html",
    "techdocs/current/l2vpn/l2vpn_intro.html",
    "techdocs/current/l2vpn/l2vpn_operation.html",
    "techdocs/current/l2xug/l2x_config.html",
    "techdocs/current/l2xug/l2x_intro.html",
    "techdocs/current/l2xug/l2x_operation.html",
    "techdocs/current/l3vpnug/l3vpn_config_cmds.html",
    "techdocs/current/l3vpnug/l3vpn_intro.html",
    "techdocs/current/l3vpnug/l3vpn_operation_cmds.html",
    "techdocs/current/lag/lag_config.html",
    "techdocs/current/lag/lag_operation_cmds.html",
    "techdocs/current/lag/lag_overview.html",
    "techdocs/current/ldpug-l2vpn/ldp_l2vpn_config.html",
    "techdocs/current/ldpug-l2vpn/ldp_l2vpn_intro.html",
    "techdocs/current/ldpug-l2vpn/ldp_l2vpn_operation.html",
    "techdocs/current/ldpug/ldp_config.html",
    "techdocs/current/ldpug/ldp_operation.html",
    "techdocs/current/ldpug/ldp_overview.html",
    "techdocs/current/led/led_intro.html",
    "techdocs/current/led/led_network_port.html",
    "techdocs/current/li/li_etsi_x1.html",
    "techdocs/current/li/li_intro.html",
    "techdocs/current/li/li_operational_state_api.html",
    "techdocs/current/li/li_radius.html",
    "techdocs/current/lldpug/lldp_config.html",
    "techdocs/current/lldpug/lldp_intro.html",
    "techdocs/current/lldpug/lldp_operation.html",
    "techdocs/current/loggingug/logging_config.html",
    "techdocs/current/loggingug/logging_intro.html",
    "techdocs/current/loggingug/logging_operation.html",
    "techdocs/current/loggingug/logging_reference.html",
    "techdocs/current/lum/lum_config.html",
    "techdocs/current/lum/lum_intro.html",
    "techdocs/current/lum/lum_operation_cmds.html",
    "techdocs/current/mirroringug/mirroring_config.html",
    "techdocs/current/mirroringug/mirroring_intro.html",
    "techdocs/current/mirroringug/mirroring_operation.html",
    "techdocs/current/mvpnug/mvpn_config.html",
    "techdocs/current/mvpnug/mvpn_intro.html",
    "techdocs/current/mvpnug/mvpn_operation.html",
    "techdocs/current/ngaccess/access_config_aaa_profile.html",
    "techdocs/current/ngaccess/access_config_access_profile.html",
    "techdocs/current/ngaccess/access_config_dhcp_server.html",
    "techdocs/current/ngaccess/access_config_example.html",
    "techdocs/current/ngaccess/access_config_interface.html",
    "techdocs/current/ngaccess/access_config_l2tp_pool.html",
    "techdocs/current/ngaccess/access_config_l2tp_profile.html",
    "techdocs/current/ngaccess/access_config_marking.html",
    "techdocs/current/ngaccess/access_config_overview.html",
    "techdocs/current/ngaccess/access_config_pool.html",
    "techdocs/current/ngaccess/access_config_radius_profile.html",
    "techdocs/current/ngaccess/access_config_radius_server.html",
    "techdocs/current/ngaccess/access_config_service_profile.html",
    "techdocs/current/ngaccess/access_config_user_profile.html",
    "techdocs/current/ngaccess/access_intro.html",
    "techdocs/current/ngaccess/access_operations.html",
    "techdocs/current/ngaccess/access_standards.html",
    "techdocs/current/ntpug/ntp_config_cmds.html",
    "techdocs/current/ntpug/ntp_intro.html",
    "techdocs/current/ntpug/ntp_operation_cmds.html",
    "techdocs/current/ospf/ospf_config.html",
    "techdocs/current/ospf/ospf_intro.html",
    "techdocs/current/ospf/ospf_operation.html",
    "techdocs/current/pimug/pim_config.html",
    "techdocs/current/pimug/pim_intro.html",
    "techdocs/current/pimug/pim_operation.html",
    "techdocs/current/ping-traceroute/ping_traceroute_intro.html",
    "techdocs/current/ping-traceroute/ping_traceroute_operation_cmds.html",
    "techdocs/current/platform/feature_support_matrix.html",
    "techdocs/current/platform/firmware_versions.html",
    "techdocs/current/platform/intro.html",
    "techdocs/current/platform/rbfs_edgecore_agr400.html",
    "techdocs/current/platform/rbfs_edgecore_agr420.html",
    "techdocs/current/platform/rbfs_edgecore_csr440.html",
    "techdocs/current/platform/rbfs_ufispace_s9500_22xst.html",
    "techdocs/current/platform/rbfs_ufispace_s9510_28dc.html",
    "techdocs/current/platform/rbfs_ufispace_s9600_102xc.html",
    "techdocs/current/platform/rbfs_ufispace_s9600_32x.html",
    "techdocs/current/platform/rbfs_ufispace_s9600_72xc.html",
    "techdocs/current/platform/resource_limit.html",
    "techdocs/current/policyug/policy_config.html",
    "techdocs/current/policyug/policy_intro.html",
    "techdocs/current/policyug/policy_operations.html",
    "techdocs/current/prodoverview/rbfs_overview_guide.html",
    "techdocs/current/radiusservices/appendix-b.html",
    "techdocs/current/radiusservices/appendix_a.html",
    "techdocs/current/radiusservices/appendix_c.html",
    "techdocs/current/radiusservices/radius_accounting.html",
    "techdocs/current/radiusservices/radius_accounting_adjustment_config.html",
    "techdocs/current/radiusservices/radius_control.html",
    "techdocs/current/radiusservices/radius_counters.html",
    "techdocs/current/radiusservices/radius_redundancy.html",
    "techdocs/current/radiusservices/radiusservices_intro.html",
    "techdocs/current/radiusservices/solution_overview.html",
    "techdocs/current/radiusservices/test_aaa.html",
    "techdocs/current/redundancy/rbfs_redundancy_config_cmds.html",
    "techdocs/current/redundancy/rbfs_redundancy_intro.html",
    "techdocs/current/redundancy/rbfs_redundancy_operation_cmds.html",
    "techdocs/current/refdesign-cgnat/cbng_cgnat_refdesign_appendixes.html",
    "techdocs/current/refdesign-cgnat/cbng_cgnat_refdesign_config_protocols.html",
    "techdocs/current/refdesign-cgnat/cbng_cgnat_refdesign_config_settings.html",
    "techdocs/current/refdesign-cgnat/cbng_cgnat_refdesign_nat_config.html",
    "techdocs/current/refdesign-cgnat/cbng_cgnat_refdesign_overview.html",
    "techdocs/current/refdesign-cgnat/cbng_cgnat_refdesign_pppoe_subscriber_mgmt.html",
    "techdocs/current/refdesign-ha/cbngipoe-rd-config.html",
    "techdocs/current/refdesign-ha/cbngipoe-rd-overview.html",
    "techdocs/current/refdesign-ha/cbngipoe_rd_refdesign_appendixes.html",
    "techdocs/current/refdesign-ha/cbngipoe_refdesign_config_protocols.html",
    "techdocs/current/refdesign-ha/cbngipoe_refdesign_config_settings.html",
    "techdocs/current/refdesign-ha/cbngipoe_refdesign_ipoe_subscriber_mgmt.html",
    "techdocs/current/refdesign-pppoe/cbngpppoe_refdesign_appendixes.html",
    "techdocs/current/refdesign-pppoe/cbngpppoe_refdesign_config_protocols.html",
    "techdocs/current/refdesign-pppoe/cbngpppoe_refdesign_config_settings.html",
    "techdocs/current/refdesign-pppoe/cbngpppoe_refdesign_overview.html",
    "techdocs/current/refdesign-pppoe/cbngpppoe_refdesign_pppoe_subscriber_mgmt.html",
    "techdocs/current/refdesign/_attachments/blaster.json.html",
    "techdocs/current/refdesign/_attachments/ospf_3node.json.html",
    "techdocs/current/refdesign/cbngipoe_refdesign_appendixes.html",
    "techdocs/current/refdesign/cbngipoe_refdesign_config_protocols.html",
    "techdocs/current/refdesign/cbngipoe_refdesign_config_settings.html",
    "techdocs/current/refdesign/cbngipoe_refdesign_ipoe_subscriber_mgmt.html",
    "techdocs/current/refdesign/cbngipoe_refdesign_overview.html",
    "techdocs/current/resmonug/resmon_config_cmds.html",
    "techdocs/current/resmonug/resmon_intro.html",
    "techdocs/current/resmonug/resmon_operation_cmds.html",
    "techdocs/current/ribug/rib-operational-commands.html",
    "techdocs/current/ribug/rib-overview.html",
    "techdocs/current/routeleak/routeleak_operation.html",
    "techdocs/current/scpug/scp_config.html",
    "techdocs/current/scpug/scp_intro.html",
    "techdocs/current/scpug/scp_operations.html",
    "techdocs/current/secmgmt/secmgmt_intro.html",
    "techdocs/current/secmgmt/secmgmt_rbac.html",
    "techdocs/current/secmgmt/secmgmt_rbfs_token.html",
    "techdocs/current/secmgmt/secmgmt_ssh_tacacs.html",
    "techdocs/current/sflowug/sflow_config.html",
    "techdocs/current/sflowug/sflow_operations.html",
    "techdocs/current/sflowug/sflow_overview.html",
    "techdocs/current/snmpug/snmp_config.html",
    "techdocs/current/snmpug/snmp_overview.html",
    "techdocs/current/staticroutingug/staticrouting_config.html",
    "techdocs/current/staticroutingug/staticrouting_intro.html",
    "techdocs/current/staticroutingug/staticrouting_operation.html",
    "techdocs/current/subscriber-filters/subscriber-filters-commands.html",
    "techdocs/current/subscriber-filters/subscriber-filters-config.html",
    "techdocs/current/subscriber-filters/subscriber-filters-overview.html",
    "techdocs/current/tools/installation_overview.html",
    "techdocs/current/tools/licensing.html",
    "techdocs/current/tools/lifecycle-operational-cmds.html",
    "techdocs/current/tools/manual_installation.html",
    "techdocs/current/tools/rbfs-ztp.html",
    "techdocs/current/tools/software_download.html",
    "techdocs/current/trbl/appln_layer.html",
    "techdocs/current/trbl/intro.html",
    "techdocs/current/trbl/logging.html",
    "techdocs/current/trbl/physical_layer.html",
    "techdocs/current/trbl/reporting_issues.html",
    "techdocs/current/trbl/system_health.html",
    "techdocs/current/tsdb/tsdb_config.html",
    "techdocs/current/tsdb/tsdb_intro.html",
    "techdocs/current/tsdb/tsdb_operations.html",
    "trainings/current/index.html"
  ],
  "cache_ttl_seconds": 3600,
  "request_timeout": 30,
  "max_retries": 3,
  "log_level": "INFO"
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
