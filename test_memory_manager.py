#!/usr/bin/env python3
"""
Comprehensive test suite for the production-grade Memory Manager.

Covers:
    - CRUD operations
    - Input validation
    - Full-text search (FTS5)
    - Tag-based filtering
    - Pagination
    - Concurrency / thread-safety
    - Data integrity verification
    - JSON -> SQLite migration
    - Error handling & edge cases
    - Statistics
"""

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from memory_manager import (
    MAX_KEY_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TAGS_PER_MEMORY,
    MAX_VALUE_SIZE,
    MemoryEntry,
    MemoryManager,
    MemoryManagerError,
    MemoryNotFoundError,
    MemoryStorageError,
    MemoryValidationError,
    SQLiteStorage,
    _validate_key,
    _validate_tags,
    _validate_value,
    migrate_from_json,
)


class _TempDBMixin:
    """Mixin that creates a temp database for each test and cleans up after."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmpdir, "test_memories.db")
        self.manager = MemoryManager(db_path=self.db_path)

    def tearDown(self):
        self.manager.close()
        for f in Path(self._tmpdir).glob("*"):
            f.unlink(missing_ok=True)
        Path(self._tmpdir).rmdir()


# =========================================================================
# 1. CRUD Operations
# =========================================================================


class TestStoreMemory(_TempDBMixin, unittest.TestCase):
    """Tests for store_memory()."""

    def test_store_returns_memory_entry(self):
        entry = self.manager.store_memory("k1", "hello world", ["tag1"])
        self.assertIsInstance(entry, MemoryEntry)
        self.assertEqual(entry.key, "k1")
        self.assertEqual(entry.value, "hello world")
        self.assertEqual(entry.tags, ["tag1"])

    def test_store_without_tags(self):
        entry = self.manager.store_memory("k1", "value")
        self.assertEqual(entry.tags, [])

    def test_store_generates_hash(self):
        entry = self.manager.store_memory("k1", "test")
        self.assertEqual(len(entry.hash), 64)  # SHA256 hex

    def test_store_overwrites_existing(self):
        self.manager.store_memory("k1", "v1", ["a"])
        entry = self.manager.store_memory("k1", "v2", ["b"])
        self.assertEqual(entry.value, "v2")
        self.assertEqual(entry.tags, ["b"])

    def test_store_preserves_original_timestamp_on_update(self):
        e1 = self.manager.store_memory("k1", "v1")
        e2 = self.manager.store_memory("k1", "v2")
        self.assertEqual(e1.timestamp, e2.timestamp)
        self.assertNotEqual(e1.updated_at, e2.updated_at)


class TestRetrieveMemory(_TempDBMixin, unittest.TestCase):
    """Tests for retrieve_memory()."""

    def test_retrieve_existing(self):
        self.manager.store_memory("k1", "hello")
        entry = self.manager.retrieve_memory("k1")
        self.assertEqual(entry.value, "hello")

    def test_retrieve_nonexistent_raises(self):
        with self.assertRaises(MemoryNotFoundError):
            self.manager.retrieve_memory("nope")

    def test_retrieve_returns_tags(self):
        self.manager.store_memory("k1", "v", ["t1", "t2"])
        entry = self.manager.retrieve_memory("k1")
        self.assertCountEqual(entry.tags, ["t1", "t2"])


class TestDeleteMemory(_TempDBMixin, unittest.TestCase):
    """Tests for delete_memory()."""

    def test_delete_existing(self):
        self.manager.store_memory("k1", "v")
        self.assertTrue(self.manager.delete_memory("k1"))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.manager.delete_memory("nope"))

    def test_delete_removes_from_search(self):
        self.manager.store_memory("k1", "findable text")
        self.manager.delete_memory("k1")
        results = self.manager.search_memories(query="findable")
        self.assertEqual(len(results), 0)

    def test_delete_removes_tags(self):
        self.manager.store_memory("k1", "v", ["tag1"])
        self.manager.delete_memory("k1")
        keys = self.manager.list_memories(tag="tag1")
        self.assertEqual(len(keys), 0)


class TestListMemories(_TempDBMixin, unittest.TestCase):
    """Tests for list_memories()."""

    def test_list_empty(self):
        self.assertEqual(self.manager.list_memories(), [])

    def test_list_returns_keys(self):
        self.manager.store_memory("a", "v1")
        self.manager.store_memory("b", "v2")
        keys = self.manager.list_memories()
        self.assertCountEqual(keys, ["a", "b"])

    def test_list_filter_by_tag(self):
        self.manager.store_memory("a", "v1", ["x"])
        self.manager.store_memory("b", "v2", ["y"])
        keys = self.manager.list_memories(tag="x")
        self.assertEqual(keys, ["a"])

    def test_list_pagination(self):
        for i in range(5):
            self.manager.store_memory(f"k{i}", f"v{i}")
        page1 = self.manager.list_memories(limit=2, offset=0)
        page2 = self.manager.list_memories(limit=2, offset=2)
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertNotEqual(set(page1), set(page2))


# =========================================================================
# 2. Input Validation
# =========================================================================


class TestValidation(unittest.TestCase):
    """Tests for input validation functions and MemoryManager validation."""

    def test_validate_key_empty(self):
        with self.assertRaises(MemoryValidationError):
            _validate_key("")

    def test_validate_key_blank(self):
        with self.assertRaises(MemoryValidationError):
            _validate_key("   ")

    def test_validate_key_too_long(self):
        with self.assertRaises(MemoryValidationError):
            _validate_key("x" * (MAX_KEY_LENGTH + 1))

    def test_validate_key_non_string(self):
        with self.assertRaises(MemoryValidationError):
            _validate_key(123)  # type: ignore

    def test_validate_key_valid(self):
        _validate_key("valid_key")  # should not raise

    def test_validate_value_non_string(self):
        with self.assertRaises(MemoryValidationError):
            _validate_value(42)  # type: ignore

    def test_validate_value_too_large(self):
        with self.assertRaises(MemoryValidationError):
            _validate_value("x" * (MAX_VALUE_SIZE + 1))

    def test_validate_tags_not_list(self):
        with self.assertRaises(MemoryValidationError):
            _validate_tags("not-a-list")  # type: ignore

    def test_validate_tags_too_many(self):
        with self.assertRaises(MemoryValidationError):
            _validate_tags(["t"] * (MAX_TAGS_PER_MEMORY + 1))

    def test_validate_tags_non_string_element(self):
        with self.assertRaises(MemoryValidationError):
            _validate_tags([123])  # type: ignore

    def test_validate_tags_too_long(self):
        with self.assertRaises(MemoryValidationError):
            _validate_tags(["x" * (MAX_TAG_LENGTH + 1)])

    def test_validate_tags_strips_and_lowercases(self):
        result = _validate_tags(["  Hello ", " WORLD "])
        self.assertEqual(result, ["hello", "world"])

    def test_validate_tags_none_returns_empty(self):
        self.assertEqual(_validate_tags(None), [])

    def test_validate_tags_blank_skipped(self):
        result = _validate_tags(["valid", "  ", ""])
        self.assertEqual(result, ["valid"])


class TestValidationIntegration(_TempDBMixin, unittest.TestCase):
    """Validation through the MemoryManager public API."""

    def test_store_invalid_key_raises(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.store_memory("", "value")

    def test_store_invalid_value_raises(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.store_memory("k", 123)  # type: ignore

    def test_retrieve_invalid_key_raises(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.retrieve_memory("")

    def test_delete_invalid_key_raises(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.delete_memory("")

    def test_list_invalid_limit(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.list_memories(limit=0)

    def test_list_invalid_offset(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.list_memories(offset=-1)

    def test_search_invalid_limit(self):
        with self.assertRaises(MemoryValidationError):
            self.manager.search_memories(query="x", limit=2000)


# =========================================================================
# 3. Search (FTS5 + tag)
# =========================================================================


class TestSearch(_TempDBMixin, unittest.TestCase):
    """Tests for search_memories() -- full-text and tag-based."""

    def test_fts_query(self):
        self.manager.store_memory("k1", "The quick brown fox")
        self.manager.store_memory("k2", "Lazy dog sleeping")
        results = self.manager.search_memories(query="fox")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].key, "k1")

    def test_tag_only_search(self):
        self.manager.store_memory("k1", "v1", ["alpha"])
        self.manager.store_memory("k2", "v2", ["beta"])
        results = self.manager.search_memories(tag="alpha")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].key, "k1")

    def test_combined_query_and_tag(self):
        self.manager.store_memory("k1", "Python programming", ["code"])
        self.manager.store_memory("k2", "Python snake", ["animals"])
        results = self.manager.search_memories(query="Python", tag="code")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].key, "k1")

    def test_search_no_results(self):
        self.manager.store_memory("k1", "hello world")
        results = self.manager.search_memories(query="nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_pagination(self):
        for i in range(10):
            self.manager.store_memory(f"k{i}", f"common word item {i}")
        page = self.manager.search_memories(query="common", limit=3, offset=0)
        self.assertEqual(len(page), 3)

    def test_search_no_query_no_tag_returns_all(self):
        self.manager.store_memory("a", "v1")
        self.manager.store_memory("b", "v2")
        results = self.manager.search_memories()
        self.assertEqual(len(results), 2)


# =========================================================================
# 4. Analyze & Integrity
# =========================================================================


class TestAnalyzeAndIntegrity(_TempDBMixin, unittest.TestCase):
    """Tests for analyze_memory() and verify_integrity()."""

    def test_analyze_returns_expected_fields(self):
        self.manager.store_memory("k1", "test value", ["t1"])
        analysis = self.manager.analyze_memory("k1")
        self.assertIn("key", analysis)
        self.assertIn("value", analysis)
        self.assertIn("stored_at", analysis)
        self.assertIn("updated_at", analysis)
        self.assertIn("tags", analysis)
        self.assertIn("hash", analysis)
        self.assertIn("integrity_verified", analysis)
        self.assertIn("age_seconds", analysis)

    def test_analyze_integrity_passes(self):
        self.manager.store_memory("k1", "check me")
        analysis = self.manager.analyze_memory("k1")
        self.assertTrue(analysis["integrity_verified"])

    def test_analyze_nonexistent_raises(self):
        with self.assertRaises(MemoryNotFoundError):
            self.manager.analyze_memory("nope")

    def test_verify_integrity_passes(self):
        self.manager.store_memory("k1", "hello")
        self.assertTrue(self.manager.verify_integrity("k1"))

    def test_verify_integrity_nonexistent_raises(self):
        with self.assertRaises(MemoryNotFoundError):
            self.manager.verify_integrity("nope")


# =========================================================================
# 5. Statistics
# =========================================================================


class TestStatistics(_TempDBMixin, unittest.TestCase):
    """Tests for get_statistics()."""

    def test_stats_empty(self):
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_memories"], 0)
        self.assertEqual(stats["total_tags"], 0)
        self.assertEqual(stats["tags"], [])
        self.assertEqual(stats["storage_backend"], "sqlite")

    def test_stats_after_stores(self):
        self.manager.store_memory("k1", "v1", ["a", "b"])
        self.manager.store_memory("k2", "v2", ["b", "c"])
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_memories"], 2)
        self.assertEqual(stats["total_tags"], 3)  # a, b, c

    def test_stats_after_delete(self):
        self.manager.store_memory("k1", "v1", ["a"])
        self.manager.delete_memory("k1")
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_memories"], 0)


# =========================================================================
# 6. MemoryEntry data class
# =========================================================================


class TestMemoryEntry(unittest.TestCase):
    """Tests for MemoryEntry."""

    def test_to_dict(self):
        e = MemoryEntry("k", "v", "2026-01-01T00:00:00", ["t1"], "abc123")
        d = e.to_dict()
        self.assertEqual(d["key"], "k")
        self.assertEqual(d["value"], "v")
        self.assertEqual(d["tags"], ["t1"])
        self.assertEqual(d["hash"], "abc123")

    def test_repr(self):
        e = MemoryEntry("k", "v", "ts", ["t"], "h")
        self.assertIn("k", repr(e))

    def test_updated_at_defaults_to_timestamp(self):
        e = MemoryEntry("k", "v", "ts", [], "h")
        self.assertEqual(e.updated_at, "ts")


# =========================================================================
# 7. Concurrency / Thread-safety
# =========================================================================


class TestConcurrency(_TempDBMixin, unittest.TestCase):
    """Thread-safety tests."""

    def test_concurrent_stores(self):
        errors = []

        def store(idx):
            try:
                self.manager.store_memory(f"thread_{idx}", f"value_{idx}", ["concurrent"])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=store, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors during concurrent store: {errors}")
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_memories"], 20)

    def test_concurrent_reads_and_writes(self):
        """Mix of reads and writes should not crash or corrupt data."""
        self.manager.store_memory("shared", "initial")
        errors = []

        def writer(idx):
            try:
                self.manager.store_memory("shared", f"updated_{idx}")
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                self.manager.retrieve_memory("shared")
            except MemoryNotFoundError:
                pass  # acceptable race
            except Exception as exc:
                errors.append(exc)

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors: {errors}")


# =========================================================================
# 8. Migration (JSON -> SQLite)
# =========================================================================


class TestMigration(unittest.TestCase):
    """Tests for migrate_from_json()."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.json_path = os.path.join(self._tmpdir, "legacy.json")
        self.db_path = os.path.join(self._tmpdir, "migrated.db")

    def tearDown(self):
        for f in Path(self._tmpdir).glob("*"):
            f.unlink(missing_ok=True)
        Path(self._tmpdir).rmdir()

    def _write_json(self, data):
        with open(self.json_path, "w") as f:
            json.dump(data, f)

    def test_migrate_success(self):
        self._write_json({
            "task_1": {
                "value": "Do homework",
                "timestamp": "2026-01-01T00:00:00",
                "tags": ["school"],
                "hash": "abc",
            },
            "task_2": {
                "value": "Read book",
                "timestamp": "2026-01-02T00:00:00",
                "tags": ["leisure"],
                "hash": "def",
            },
        })
        report = migrate_from_json(self.json_path, self.db_path)
        self.assertEqual(report["total_found"], 2)
        self.assertEqual(report["migrated"], 2)
        self.assertEqual(report["skipped"], 0)
        self.assertEqual(report["errors"], [])

        # Verify data in new DB
        manager = MemoryManager(db_path=self.db_path)
        try:
            entry = manager.retrieve_memory("task_1")
            self.assertEqual(entry.value, "Do homework")
        finally:
            manager.close()

    def test_migrate_dry_run(self):
        self._write_json({
            "k1": {"value": "v1", "tags": ["t1"]},
        })
        report = migrate_from_json(self.json_path, self.db_path, dry_run=True)
        self.assertEqual(report["migrated"], 1)
        self.assertFalse(Path(self.db_path).exists())

    def test_migrate_missing_source(self):
        report = migrate_from_json("/nonexistent/path.json", self.db_path)
        self.assertTrue(len(report["errors"]) > 0)

    def test_migrate_invalid_json(self):
        with open(self.json_path, "w") as f:
            f.write("NOT JSON{{{")
        report = migrate_from_json(self.json_path, self.db_path)
        self.assertTrue(len(report["errors"]) > 0)

    def test_migrate_skips_invalid_entries(self):
        self._write_json({
            "valid": {"value": "ok", "tags": ["t1"]},
            "": {"value": "bad key", "tags": []},
        })
        report = migrate_from_json(self.json_path, self.db_path)
        self.assertEqual(report["migrated"], 1)
        self.assertEqual(report["skipped"], 1)

    def test_migrate_non_dict_json(self):
        self._write_json([1, 2, 3])
        report = migrate_from_json(self.json_path, self.db_path)
        self.assertTrue(len(report["errors"]) > 0)


# =========================================================================
# 9. SQLiteStorage low-level
# =========================================================================


class TestSQLiteStorage(unittest.TestCase):
    """Tests for the SQLiteStorage backend directly."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmpdir, "storage_test.db")
        self.storage = SQLiteStorage(db_path=self.db_path)

    def tearDown(self):
        self.storage.close()
        for f in Path(self._tmpdir).glob("*"):
            f.unlink(missing_ok=True)
        Path(self._tmpdir).rmdir()

    def test_insert_and_get(self):
        entry = MemoryEntry("k1", "val", "2026-01-01", ["t"], "h", "2026-01-01")
        self.storage.insert(entry)
        got = self.storage.get("k1")
        self.assertIsNotNone(got)
        self.assertEqual(got.value, "val")

    def test_get_nonexistent(self):
        self.assertIsNone(self.storage.get("nope"))

    def test_delete(self):
        entry = MemoryEntry("k1", "val", "ts", [], "h", "ts")
        self.storage.insert(entry)
        self.assertTrue(self.storage.delete("k1"))
        self.assertIsNone(self.storage.get("k1"))

    def test_count(self):
        self.assertEqual(self.storage.count(), 0)
        self.storage.insert(MemoryEntry("a", "v", "ts", [], "h", "ts"))
        self.assertEqual(self.storage.count(), 1)

    def test_all_tags(self):
        self.storage.insert(MemoryEntry("a", "v", "ts", ["x", "y"], "h", "ts"))
        tags = self.storage.all_tags()
        tag_names = [t["tag"] for t in tags]
        self.assertCountEqual(tag_names, ["x", "y"])


# =========================================================================
# 10. Edge Cases
# =========================================================================


class TestEdgeCases(_TempDBMixin, unittest.TestCase):
    """Edge case and boundary tests."""

    def test_store_max_length_key(self):
        key = "k" * MAX_KEY_LENGTH
        entry = self.manager.store_memory(key, "value")
        self.assertEqual(entry.key, key)

    def test_store_unicode_value(self):
        entry = self.manager.store_memory("k1", "Hello world in Japanese")
        self.assertEqual(entry.value, "Hello world in Japanese")

    def test_store_empty_value(self):
        entry = self.manager.store_memory("k1", "")
        self.assertEqual(entry.value, "")

    def test_store_special_chars_in_value(self):
        val = "Line1\nLine2\tTabbed <html>&amp;</html>"
        entry = self.manager.store_memory("k1", val)
        retrieved = self.manager.retrieve_memory("k1")
        self.assertEqual(retrieved.value, val)

    def test_tags_normalized_to_lowercase(self):
        entry = self.manager.store_memory("k1", "v", ["UPPER", "MiXeD"])
        self.assertCountEqual(entry.tags, ["upper", "mixed"])

    def test_close_and_reopen(self):
        self.manager.store_memory("k1", "persistent")
        self.manager.close()
        # Reopen
        manager2 = MemoryManager(db_path=self.db_path)
        try:
            entry = manager2.retrieve_memory("k1")
            self.assertEqual(entry.value, "persistent")
        finally:
            manager2.close()

    def test_manager_close_idempotent(self):
        self.manager.close()
        self.manager.close()  # should not raise


if __name__ == "__main__":
    unittest.main()
