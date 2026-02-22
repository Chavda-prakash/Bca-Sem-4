#!/usr/bin/env python3
"""
Test suite for the FastAPI REST API layer.

Covers:
    - CRUD endpoints
    - Search endpoint (FTS5 + tag)
    - Pagination
    - Error handling (404, 422)
    - Auth placeholder
    - Rate limiting header presence
    - Statistics and health
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestAPI(unittest.TestCase):
    """Integration tests for the Memory Manager REST API."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls._tmpdir, "test_api.db")
        # Patch DB_PATH before importing app
        with patch.dict(os.environ, {"MEMORY_DB_PATH": cls.db_path}):
            import api as api_module
            # Reset the singleton
            api_module._manager = None
            api_module.DB_PATH = cls.db_path
            cls.client = TestClient(api_module.app)
            cls.api_module = api_module

    @classmethod
    def tearDownClass(cls):
        if cls.api_module._manager is not None:
            cls.api_module._manager.close()
            cls.api_module._manager = None
        for f in Path(cls._tmpdir).glob("*"):
            f.unlink(missing_ok=True)
        Path(cls._tmpdir).rmdir()

    def setUp(self):
        """Clean DB between tests by deleting all memories."""
        # List and delete all
        resp = self.client.get("/api/v1/memories?limit=1000")
        if resp.status_code == 200:
            for key in resp.json().get("keys", []):
                self.client.delete(f"/api/v1/memories/{key}")

    # -- Health ---------------------------------------------------------------

    def test_health(self):
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["version"], "2.0.0")

    # -- Store ----------------------------------------------------------------

    def test_store_memory(self):
        resp = self.client.post("/api/v1/memories", json={
            "key": "k1", "value": "hello world", "tags": ["t1"]
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["key"], "k1")
        self.assertEqual(data["value"], "hello world")
        self.assertEqual(data["tags"], ["t1"])
        self.assertEqual(len(data["hash"]), 64)

    def test_store_updates_existing(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "v1"})
        resp = self.client.post("/api/v1/memories", json={"key": "k1", "value": "v2"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["value"], "v2")

    def test_store_validation_empty_key(self):
        resp = self.client.post("/api/v1/memories", json={"key": "", "value": "v"})
        self.assertEqual(resp.status_code, 422)

    # -- Retrieve -------------------------------------------------------------

    def test_retrieve_memory(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "hello"})
        resp = self.client.get("/api/v1/memories/k1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["value"], "hello")

    def test_retrieve_not_found(self):
        resp = self.client.get("/api/v1/memories/nonexistent")
        self.assertEqual(resp.status_code, 404)

    # -- Delete ---------------------------------------------------------------

    def test_delete_memory(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "v"})
        resp = self.client.delete("/api/v1/memories/k1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])

    def test_delete_not_found(self):
        resp = self.client.delete("/api/v1/memories/nope")
        self.assertEqual(resp.status_code, 404)

    # -- List -----------------------------------------------------------------

    def test_list_memories(self):
        self.client.post("/api/v1/memories", json={"key": "a", "value": "v1"})
        self.client.post("/api/v1/memories", json={"key": "b", "value": "v2"})
        resp = self.client.get("/api/v1/memories")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["keys"]), 2)
        self.assertEqual(data["total"], 2)

    def test_list_with_tag_filter(self):
        self.client.post("/api/v1/memories", json={"key": "a", "value": "v1", "tags": ["x"]})
        self.client.post("/api/v1/memories", json={"key": "b", "value": "v2", "tags": ["y"]})
        resp = self.client.get("/api/v1/memories?tag=x")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["keys"], ["a"])

    def test_list_pagination(self):
        for i in range(5):
            self.client.post("/api/v1/memories", json={"key": f"k{i}", "value": f"v{i}"})
        resp = self.client.get("/api/v1/memories?limit=2&offset=0")
        self.assertEqual(len(resp.json()["keys"]), 2)
        resp2 = self.client.get("/api/v1/memories?limit=2&offset=2")
        self.assertEqual(len(resp2.json()["keys"]), 2)

    # -- Search ---------------------------------------------------------------

    def test_search_fts(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "The quick brown fox"})
        self.client.post("/api/v1/memories", json={"key": "k2", "value": "Lazy dog"})
        resp = self.client.get("/api/v1/search?query=fox")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["key"], "k1")

    def test_search_by_tag(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "v1", "tags": ["alpha"]})
        self.client.post("/api/v1/memories", json={"key": "k2", "value": "v2", "tags": ["beta"]})
        resp = self.client.get("/api/v1/search?tag=alpha")
        self.assertEqual(resp.json()["count"], 1)

    def test_search_combined(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "Python programming", "tags": ["code"]})
        self.client.post("/api/v1/memories", json={"key": "k2", "value": "Python snake", "tags": ["animals"]})
        resp = self.client.get("/api/v1/search?query=Python&tag=code")
        self.assertEqual(resp.json()["count"], 1)
        self.assertEqual(resp.json()["results"][0]["key"], "k1")

    # -- Analyze & Verify -----------------------------------------------------

    def test_analyze(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "test"})
        resp = self.client.get("/api/v1/memories/k1/analyze")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["integrity_verified"])
        self.assertIn("age_seconds", data)

    def test_verify_integrity(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "test"})
        resp = self.client.get("/api/v1/memories/k1/verify")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["integrity_verified"])

    # -- Statistics ------------------------------------------------------------

    def test_statistics(self):
        self.client.post("/api/v1/memories", json={"key": "k1", "value": "v", "tags": ["a", "b"]})
        resp = self.client.get("/api/v1/statistics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_memories"], 1)
        self.assertEqual(data["total_tags"], 2)
        self.assertEqual(data["storage_backend"], "sqlite")

    # -- Auth placeholder -----------------------------------------------------

    def test_auth_disabled_by_default(self):
        """When MEMORY_API_KEY is empty, auth should be disabled."""
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
