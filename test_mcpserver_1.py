import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import mcpserver_opt_1 as mod


class TestValidateRtbrickUrl(unittest.TestCase):
    def test_allows_valid_https_rtbrick_domain(self) -> None:
        ok, msg = mod.validate_rtbrick_url("https://www.rtbrick.com/some/page")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_rejects_non_https_scheme(self) -> None:
        ok, msg = mod.validate_rtbrick_url("http://www.rtbrick.com/")
        self.assertFalse(ok)
        self.assertIn("Only https:// URLs are allowed", msg)

    def test_rejects_unknown_domain(self) -> None:
        ok, msg = mod.validate_rtbrick_url("https://example.com/")
        self.assertFalse(ok)
        self.assertIn("allowlist", msg)


class TestExtractTextFromHtml(unittest.TestCase):
    def test_extracts_readable_text_and_skips_script(self) -> None:
        html = """
        <html>
          <head><title>Test</title></head>
          <body>
            <h1>Title</h1>
            <p>Hello <b>world</b></p>
            <script>console.log("should be skipped")</script>
          </body>
        </html>
        """
        text = mod.extract_text_from_html(html)
        self.assertIn("Title", text)
        self.assertIn("Hello world", text)
        self.assertNotIn("should be skipped", text)


class TestCacheEntryAndDocumentCache(unittest.TestCase):
    def test_cache_entry_expiry(self) -> None:
        now = datetime.now()
        old_ts = now - timedelta(seconds=5)
        entry = mod.CacheEntry(content="x", timestamp=old_ts, url="u")

        self.assertTrue(entry.is_expired(ttl_seconds=1))
        self.assertFalse(entry.is_expired(ttl_seconds=10))

    def test_document_cache_put_get_and_evict(self) -> None:
        cache = mod.DocumentCache(max_size=1, ttl_seconds=60)

        cache.put("k1", "v1", "url1")
        self.assertEqual(cache.get("k1"), "v1")
        stats = cache.stats()
        self.assertEqual(stats["entries"], 1)

        cache.put("k2", "v2", "url2")
        self.assertIsNone(cache.get("k1"))
        self.assertEqual(cache.get("k2"), "v2")


class TestSearchDocuments(unittest.TestCase):
    def test_search_documents_ranks_and_returns_context(self) -> None:
        docs = {
            "doc1.html": "This is a RTBrick document about BGP and routing.",
            "doc2.html": "Unrelated content with no useful keywords.",
            "bgp_intro.html": "BGP basics. BGP is a routing protocol. More about BGP here.",
        }
        hits = mod.search_documents("BGP", docs, context_lines=1, max_results=5)

        self.assertGreaterEqual(len(hits), 1)
        top = hits[0]
        self.assertEqual(top.doc_path, "bgp_intro.html")
        self.assertIn("BGP", top.context)


class TestLoadConfig(unittest.TestCase):
    def test_load_config_uses_config_path_env_when_present(self) -> None:
        data = {
            "doc_paths": ["custom1.html", "custom2.html"],
            "base_url": "https://documents.rtbrick.com/custom/",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)

            with patch.dict(os.environ, {"CONFIG_PATH": cfg_path}, clear=False):
                loaded = mod.load_config()

        self.assertEqual(loaded.get("doc_paths"), data["doc_paths"])
        self.assertEqual(loaded.get("base_url"), data["base_url"])


class TestMCPServerBasics(unittest.TestCase):
    @patch.object(mod, "load_config", return_value={})
    def test_server_initialization_uses_defaults(self, _mock_load_config: MagicMock) -> None:
        server = mod.MCPServer()
        self.assertEqual(server.tech_doc_paths, mod.DEFAULT_TECH_DOC_PATHS)
        self.assertEqual(server.tech_docs_base_url, mod.RTBRICK_TECHDOCS_BASE_URL)

    @patch.object(mod, "load_config", return_value={})
    def test_tools_schema_contains_expected_tools(self, _mock_load_config: MagicMock) -> None:
        server = mod.MCPServer()
        tools = server._tools_schema()
        names = {t["name"] for t in tools}
        self.assertIn("fetch_rtbrick_page", names)
        self.assertIn("search_tech_docs", names)

    @patch.object(mod, "load_config", return_value={})
    def test_handle_initialize_and_tools_list(self, _mock_load_config: MagicMock) -> None:
        server = mod.MCPServer()

        init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        init_resp = server.handle_request(init_req)
        self.assertIsNotNone(init_resp)
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "rtbrick-mcp-server")

        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        list_resp = server.handle_request(list_req)
        self.assertIsNotNone(list_resp)
        self.assertIn("tools", list_resp["result"])

    @patch.object(mod, "load_config", return_value={})
    def test_handle_tools_call_validation_and_unknown_tool(
        self,
        _mock_load_config: MagicMock,
    ) -> None:
        server = mod.MCPServer()

        bad_fetch_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "fetch_rtbrick_page", "arguments": {}},
        }
        bad_resp = server.handle_request(bad_fetch_req)
        self.assertIsNotNone(bad_resp)
        self.assertEqual(bad_resp["error"]["code"], server.INVALID_PARAMS)

        unknown_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        unknown_resp = server.handle_request(unknown_req)
        self.assertIsNotNone(unknown_resp)
        self.assertEqual(unknown_resp["error"]["code"], server.METHOD_NOT_FOUND)


class TestMCPServerToolImplementations(unittest.TestCase):
    @patch.object(mod, "load_config", return_value={})
    def test_tool_list_tech_docs_outputs_expected_header(self, _mock_load_config: MagicMock) -> None:
        server = mod.MCPServer()
        output = server.tool_list_tech_docs()
        self.assertIn("RTBrick Technical Documentation Pages", output)
        self.assertIn(server.tech_docs_base_url, output)

    @patch.object(mod, "load_config", return_value={})
    def test_fetch_url_uses_cache_before_http(
        self,
        _mock_load_config: MagicMock,
    ) -> None:
        server = mod.MCPServer()
        url = "https://www.rtbrick.com/some/page"

        server.cache.put(url, "cached content", url=url)

        with patch.object(server.http, "get") as mock_get:
            content, err = server._fetch_url(url)

        self.assertIsNone(err)
        self.assertEqual(content, "cached content")
        mock_get.assert_not_called()

    @patch.object(mod, "load_config", return_value={})
    def test_fetch_url_rejects_invalid_domain(
        self,
        _mock_load_config: MagicMock,
    ) -> None:
        server = mod.MCPServer()
        content, err = server._fetch_url("https://example.com/not-allowed")
        self.assertIsNone(content)
        self.assertIsInstance(err, str)
        self.assertIn("allowlist", err)


if __name__ == "__main__":
    unittest.main()

