# Changelog

All notable changes to the RTBrick MCP Server are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

---

## [3.0.0] — Unreleased

Rewritten on the official MCP Python SDK 2.x (`MCPServer`, formerly FastMCP). Requires Python 3.10+.

### Added
- Training material (https://www.rtbrick.com/docs/trainings/current/index.html) alongside the tech docs
- Version support: the newest patch of each of the 5 most recent RBFS release lines
  (`RTBRICK_MCP_MAX_VERSIONS`), discovered automatically from the site's sitemaps
- `search_docs` — BM25 search over page sections with per-word matching, so multi-word queries
  no longer need to appear verbatim; results link straight to the section (`#anchor`)
- `get_doc_page` — read a page or a single section, by link or path, for any available version,
  paginated with `offset` / `max_chars`
- `list_doc_versions` and `list_doc_pages`
- On-disk page cache (`~/.cache/rtbrick-mcp`) and background indexing of the current docs at startup
- Streamable HTTP transport (`--transport streamable-http`)
- Test suite under `tests/` that runs offline

### Changed
- All ~320 pages per version are covered, discovered from the sitemaps, instead of a fixed list of 23
- Docs are read from https://www.rtbrick.com/docs/ (documents.rtbrick.com now redirects there)
- Only the page's article content is extracted; code blocks keep their indentation and tables
  keep one row per line
- `get_rtbrick_website`, `get_tech_docs_index`, `search_tech_docs` and `list_tech_docs` are
  replaced by the tools above; `fetch_rtbrick_page` remains for the rest of www.rtbrick.com
- `config.json` is replaced by environment variables (see README)

### Fixed
- Packaging: the build backend didn't exist and the `rtb-mcp` entry point pointed at a missing package
- Protocol: `ping` is answered, tool failures are reported with `isError`, and protocol versions are
  negotiated (all handled by the SDK)
- Redirects are checked against the host allowlist at every hop; responses are capped at 10 MB

### Removed
- `get_rtbrick_videos` tool — returned metadata for a single video, not the playlist contents
- `get_youtube_video_info` tool — accepted any YouTube video, not only RTBrick's
- `www.youtube.com` and `youtube.com` from the domain allowlist
- `mcpserver_opt_1.py` and the duplicate `test_mcpserver_*.py` files

---

## [2.0.0] — 2026-02-27

### Added
- `get_rtbrick_videos` tool — fetches RTBrick's YouTube training-video playlist metadata via the YouTube oEmbed API (no API key required)
- `get_youtube_video_info` tool — fetches oEmbed metadata for any specific RTBrick YouTube video URL
- YouTube domain support: `www.youtube.com` and `youtube.com` added to the domain allowlist
- `RTBRICK_YOUTUBE_PLAYLIST_URL` constant pointing to the official RTBrick training playlist
- Thread-safe `DocumentCache` class with configurable TTL and LRU eviction
- `HTTPClient` wrapper with automatic retries (exponential backoff), connection pooling, and custom `User-Agent`
- Relevance-scored keyword search (`search_documents`) with context-snippet extraction and deduplication
- `validate_rtbrick_url` function — enforces `https://` scheme and domain allowlist before every request
- Optional `config.json` support with fallback to built-in defaults (23 RTBrick RBFS tech-doc pages)
- Structured logging to stderr at configurable levels (DEBUG / INFO / WARNING / ERROR)
- `smithery.yaml` for Smithery.ai MCP registry
- `mcp.json` generic MCP manifest for other registries
- `pyproject.toml` for PyPI packaging
- `requirements.txt` listing runtime dependencies

### Fixed (from original `mcpserver_opt_1.py`)
- `CONFIG` global was never assigned at module level — caused `NameError` at runtime
- `run()` indentation bug — `try/except` block was at class level, not inside the `for` loop
- `@lru_cache` on an instance method — `self` is not hashable; replaced with `DocumentCache`
- `load_config()` had dead code after `sys.exit(1)` — lines 49-51 were unreachable
- Docstrings were placed before `def` statements instead of inside methods

### Changed
- Server version bumped from `1.0.0` to `2.0.0`
- `load_config()` no longer calls `sys.exit(1)` when no config file is found — falls back to built-in defaults instead
- `fetch_rtbrick_page` description updated to mention YouTube support and JS-rendering caveat

---

## [1.0.0] — 2025-01-01

### Added
- Initial MCP server implementation
- `fetch_rtbrick_page` tool — fetch any RTBrick domain page by URL
- `get_rtbrick_website` tool — fetch https://www.rtbrick.com
- `get_tech_docs_index` tool — fetch the RTBrick tech-docs index
- `search_tech_docs` tool — keyword search across configured tech-doc pages
- `list_tech_docs` tool — list all configured documentation pages
- Domain allowlist: `www.rtbrick.com`, `rtbrick.com`, `documents.rtbrick.com`
- HTML text extraction with skip-tag support (`script`, `style`, `nav`, `footer`, `header`)
- MCP 2024-11-05 protocol support (JSON-RPC 2.0 over stdio)
- 23 RTBrick RBFS documentation pages pre-configured as defaults
