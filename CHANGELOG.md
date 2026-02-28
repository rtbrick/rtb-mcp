# Changelog

All notable changes to the RTBrick MCP Server are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

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
