#!/usr/bin/env python3
"""
Memory Manager Agent - Production-Grade Implementation
A comprehensive agent for managing, storing, and retrieving memories
with SQLite-backed persistent storage, concurrency handling, structured
indexing, input validation, and full-text search.

Author: Chavda-prakash
Version: 2.0.0
"""

import json
import logging
import hashlib
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger("memory_manager")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MemoryManagerError(Exception):
    """Base exception for all Memory Manager errors."""


class MemoryNotFoundError(MemoryManagerError):
    """Raised when a requested memory key does not exist."""


class MemoryValidationError(MemoryManagerError):
    """Raised when input validation fails."""


class MemoryStorageError(MemoryManagerError):
    """Raised when a storage (database) operation fails."""


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
MAX_KEY_LENGTH = 256
MAX_VALUE_SIZE = 1_048_576  # 1 MB
MAX_TAG_LENGTH = 128
MAX_TAGS_PER_MEMORY = 50


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class MemoryEntry:
    """Immutable representation of a stored memory."""

    __slots__ = ("key", "value", "timestamp", "tags", "hash", "updated_at")

    def __init__(
        self,
        key: str,
        value: str,
        timestamp: str,
        tags: List[str],
        hash_value: str,
        updated_at: Optional[str] = None,
    ):
        self.key = key
        self.value = value
        self.timestamp = timestamp
        self.tags = list(tags)
        self.hash = hash_value
        self.updated_at = updated_at or timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
            "hash": self.hash,
            "updated_at": self.updated_at,
        }

    def __repr__(self) -> str:
        return f"MemoryEntry(key={self.key!r}, tags={self.tags!r})"


# ---------------------------------------------------------------------------
# Storage backend (SQLite)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    hash        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_tags (
    key   TEXT NOT NULL,
    tag   TEXT NOT NULL,
    PRIMARY KEY (key, tag),
    FOREIGN KEY (key) REFERENCES memories(key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag);

-- Full-text search virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    key,
    value,
    content='memories',
    content_rowid='rowid'
);

-- Triggers to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, key, value)
    VALUES (new.rowid, new.key, new.value);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, key, value)
    VALUES ('delete', old.rowid, old.key, old.value);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, key, value)
    VALUES ('delete', old.rowid, old.key, old.value);
    INSERT INTO memories_fts(rowid, key, value)
    VALUES (new.rowid, new.key, new.value);
END;

-- Schema version tracking for migrations
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version(version) VALUES (1);
"""


class SQLiteStorage:
    """Thread-safe SQLite storage backend with WAL mode and connection pooling."""

    def __init__(self, db_path: str = "memories.db"):
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    # -- connection management ------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a thread-local connection (one per thread)."""
        conn = getattr(self._local, "connection", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return conn

    @contextmanager
    def _transaction(self):
        """Context manager that provides a cursor inside a transaction."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN")
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _init_db(self) -> None:
        """Create tables, indexes, triggers, and FTS if they don't exist."""
        conn = self._get_connection()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized at %s", self._db_path)

    # -- CRUD -----------------------------------------------------------------

    def insert(self, entry: MemoryEntry) -> None:
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO memories (key, value, timestamp, hash, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry.key, entry.value, entry.timestamp, entry.hash, entry.updated_at),
            )
            for tag in entry.tags:
                cur.execute(
                    "INSERT INTO memory_tags (key, tag) VALUES (?, ?)",
                    (entry.key, tag),
                )
        logger.debug("Inserted memory: %s", entry.key)

    def upsert(self, entry: MemoryEntry) -> None:
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO memories (key, value, timestamp, hash, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "value=excluded.value, hash=excluded.hash, updated_at=excluded.updated_at",
                (entry.key, entry.value, entry.timestamp, entry.hash, entry.updated_at),
            )
            cur.execute("DELETE FROM memory_tags WHERE key = ?", (entry.key,))
            for tag in entry.tags:
                cur.execute(
                    "INSERT INTO memory_tags (key, tag) VALUES (?, ?)",
                    (entry.key, tag),
                )
        logger.debug("Upserted memory: %s", entry.key)

    def get(self, key: str) -> Optional[MemoryEntry]:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT key, value, timestamp, hash, updated_at FROM memories WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        tags = [
            r["tag"]
            for r in conn.execute(
                "SELECT tag FROM memory_tags WHERE key = ?", (key,)
            ).fetchall()
        ]
        return MemoryEntry(
            key=row["key"],
            value=row["value"],
            timestamp=row["timestamp"],
            tags=tags,
            hash_value=row["hash"],
            updated_at=row["updated_at"],
        )

    def delete(self, key: str) -> bool:
        with self._transaction() as cur:
            cur.execute("DELETE FROM memories WHERE key = ?", (key,))
            deleted = cur.rowcount > 0
        if deleted:
            logger.debug("Deleted memory: %s", key)
        return deleted

    def list_keys(self, tag: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[str]:
        conn = self._get_connection()
        if tag:
            rows = conn.execute(
                "SELECT mt.key FROM memory_tags mt "
                "JOIN memories m ON mt.key = m.key "
                "WHERE mt.tag = ? ORDER BY m.timestamp DESC LIMIT ? OFFSET ?",
                (tag, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT key FROM memories ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [r["key"] for r in rows]

    def search(self, query: str, tag: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[MemoryEntry]:
        conn = self._get_connection()
        if tag and query:
            rows = conn.execute(
                "SELECT m.key, m.value, m.timestamp, m.hash, m.updated_at "
                "FROM memories m "
                "JOIN memories_fts fts ON m.key = fts.key "
                "JOIN memory_tags mt ON m.key = mt.key "
                "WHERE memories_fts MATCH ? AND mt.tag = ? "
                "ORDER BY rank LIMIT ? OFFSET ?",
                (query, tag, limit, offset),
            ).fetchall()
        elif query:
            rows = conn.execute(
                "SELECT m.key, m.value, m.timestamp, m.hash, m.updated_at "
                "FROM memories m "
                "JOIN memories_fts fts ON m.key = fts.key "
                "WHERE memories_fts MATCH ? "
                "ORDER BY rank LIMIT ? OFFSET ?",
                (query, limit, offset),
            ).fetchall()
        elif tag:
            rows = conn.execute(
                "SELECT m.key, m.value, m.timestamp, m.hash, m.updated_at "
                "FROM memories m "
                "JOIN memory_tags mt ON m.key = mt.key "
                "WHERE mt.tag = ? "
                "ORDER BY m.timestamp DESC LIMIT ? OFFSET ?",
                (tag, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT key, value, timestamp, hash, updated_at "
                "FROM memories ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        entries: List[MemoryEntry] = []
        for row in rows:
            tags = [
                r["tag"]
                for r in conn.execute(
                    "SELECT tag FROM memory_tags WHERE key = ?", (row["key"],)
                ).fetchall()
            ]
            entries.append(
                MemoryEntry(
                    key=row["key"],
                    value=row["value"],
                    timestamp=row["timestamp"],
                    tags=tags,
                    hash_value=row["hash"],
                    updated_at=row["updated_at"],
                )
            )
        return entries

    def count(self, tag: Optional[str] = None) -> int:
        conn = self._get_connection()
        if tag:
            row = conn.execute(
                "SELECT COUNT(DISTINCT mt.key) as cnt FROM memory_tags mt WHERE mt.tag = ?",
                (tag,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()
        return row["cnt"] if row else 0

    def all_tags(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT tag, COUNT(*) as cnt FROM memory_tags GROUP BY tag ORDER BY cnt DESC"
        ).fetchall()
        return [{"tag": r["tag"], "count": r["cnt"]} for r in rows]

    def close(self) -> None:
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            conn.close()
            self._local.connection = None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_key(key: str) -> None:
    if not isinstance(key, str):
        raise MemoryValidationError(f"Key must be a string, got {type(key).__name__}")
    if not key or not key.strip():
        raise MemoryValidationError("Key must not be empty or blank")
    if len(key) > MAX_KEY_LENGTH:
        raise MemoryValidationError(
            f"Key exceeds maximum length of {MAX_KEY_LENGTH} characters"
        )


def _validate_value(value: str) -> None:
    if not isinstance(value, str):
        raise MemoryValidationError(f"Value must be a string, got {type(value).__name__}")
    if len(value) > MAX_VALUE_SIZE:
        raise MemoryValidationError(
            f"Value exceeds maximum size of {MAX_VALUE_SIZE} bytes"
        )


def _validate_tags(tags: Optional[List[str]]) -> List[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise MemoryValidationError("Tags must be a list of strings")
    if len(tags) > MAX_TAGS_PER_MEMORY:
        raise MemoryValidationError(
            f"Too many tags (max {MAX_TAGS_PER_MEMORY}), got {len(tags)}"
        )
    cleaned: List[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            raise MemoryValidationError(f"Each tag must be a string, got {type(tag).__name__}")
        tag = tag.strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise MemoryValidationError(
                f"Tag exceeds maximum length of {MAX_TAG_LENGTH} characters"
            )
        cleaned.append(tag)
    return cleaned


# ---------------------------------------------------------------------------
# Core Memory Manager
# ---------------------------------------------------------------------------


class MemoryManager:
    """Production-grade Memory Manager with SQLite backend.

    Features:
        - SQLite storage with WAL mode for concurrent reads
        - Full-text search via FTS5
        - Thread-safe operations
        - Input validation
        - SHA256 integrity hashing
        - Structured logging
        - Pagination support
    """

    def __init__(self, db_path: str = "memories.db"):
        """Initialize the Memory Manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._storage = SQLiteStorage(db_path)
        self._lock = threading.Lock()
        logger.info("MemoryManager initialized (db=%s)", db_path)

    # -- public API -----------------------------------------------------------

    def store_memory(self, key: str, value: str, tags: Optional[List[str]] = None) -> MemoryEntry:
        """Store or update a memory entry.

        Args:
            key: Unique identifier for the memory.
            value: The memory content (string).
            tags: Optional list of tags for categorization.

        Returns:
            The stored MemoryEntry.

        Raises:
            MemoryValidationError: If inputs fail validation.
            MemoryStorageError: If the database operation fails.
        """
        _validate_key(key)
        _validate_value(value)
        clean_tags = _validate_tags(tags)

        now = datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(
            key=key,
            value=value,
            timestamp=now,
            tags=clean_tags,
            hash_value=self._generate_hash(value),
            updated_at=now,
        )

        try:
            with self._lock:
                existing = self._storage.get(key)
                if existing:
                    entry = MemoryEntry(
                        key=key,
                        value=value,
                        timestamp=existing.timestamp,
                        tags=clean_tags,
                        hash_value=self._generate_hash(value),
                        updated_at=now,
                    )
                    self._storage.upsert(entry)
                    logger.info("Updated memory: %s", key)
                else:
                    self._storage.insert(entry)
                    logger.info("Stored new memory: %s", key)
        except MemoryManagerError:
            raise
        except Exception as exc:
            logger.error("Failed to store memory %s: %s", key, exc)
            raise MemoryStorageError(f"Failed to store memory: {exc}") from exc

        return entry

    def retrieve_memory(self, key: str) -> MemoryEntry:
        """Retrieve a memory entry by key.

        Args:
            key: The memory key.

        Returns:
            The MemoryEntry.

        Raises:
            MemoryValidationError: If key is invalid.
            MemoryNotFoundError: If the key does not exist.
        """
        _validate_key(key)
        entry = self._storage.get(key)
        if entry is None:
            raise MemoryNotFoundError(f"Memory not found: {key!r}")
        logger.debug("Retrieved memory: %s", key)
        return entry

    def search_memories(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """Search memories using full-text search and/or tag filtering.

        Args:
            query: Full-text search query (FTS5 syntax supported).
            tag: Filter by tag.
            limit: Maximum results to return (default 100).
            offset: Pagination offset.

        Returns:
            List of matching MemoryEntry objects.
        """
        if limit < 1 or limit > 1000:
            raise MemoryValidationError("Limit must be between 1 and 1000")
        if offset < 0:
            raise MemoryValidationError("Offset must be non-negative")

        results = self._storage.search(query=query or "", tag=tag, limit=limit, offset=offset)
        logger.debug("Search returned %d results (query=%r, tag=%r)", len(results), query, tag)
        return results

    def analyze_memory(self, key: str) -> Dict[str, Any]:
        """Analyze a memory entry, including integrity verification.

        Args:
            key: The memory key.

        Returns:
            Analysis dict with metadata and integrity status.

        Raises:
            MemoryNotFoundError: If the key does not exist.
        """
        entry = self.retrieve_memory(key)
        expected_hash = self._generate_hash(entry.value)
        integrity_ok = entry.hash == expected_hash

        age_seconds = self._calculate_age(entry.timestamp)

        analysis = {
            "key": entry.key,
            "value": entry.value,
            "stored_at": entry.timestamp,
            "updated_at": entry.updated_at,
            "tags": entry.tags,
            "hash": entry.hash,
            "integrity_verified": integrity_ok,
            "age_seconds": round(age_seconds, 2),
        }

        if not integrity_ok:
            logger.warning("Integrity check FAILED for memory: %s", key)

        return analysis

    def delete_memory(self, key: str) -> bool:
        """Delete a memory entry.

        Args:
            key: The memory key.

        Returns:
            True if deleted, False if key did not exist.

        Raises:
            MemoryValidationError: If key is invalid.
            MemoryStorageError: If the database operation fails.
        """
        _validate_key(key)
        try:
            with self._lock:
                deleted = self._storage.delete(key)
            if deleted:
                logger.info("Deleted memory: %s", key)
            else:
                logger.debug("Delete no-op, key not found: %s", key)
            return deleted
        except MemoryManagerError:
            raise
        except Exception as exc:
            logger.error("Failed to delete memory %s: %s", key, exc)
            raise MemoryStorageError(f"Failed to delete memory: {exc}") from exc

    def list_memories(
        self,
        tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[str]:
        """List memory keys with optional tag filter and pagination.

        Args:
            tag: Filter by tag (optional).
            limit: Maximum results (default 100).
            offset: Pagination offset (default 0).

        Returns:
            List of memory keys.
        """
        if limit < 1 or limit > 1000:
            raise MemoryValidationError("Limit must be between 1 and 1000")
        if offset < 0:
            raise MemoryValidationError("Offset must be non-negative")
        return self._storage.list_keys(tag=tag, limit=limit, offset=offset)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the memory store.

        Returns:
            Dict with total_memories, tags breakdown, and storage info.
        """
        total = self._storage.count()
        tags_info = self._storage.all_tags()
        return {
            "total_memories": total,
            "total_tags": len(tags_info),
            "tags": tags_info,
            "storage_backend": "sqlite",
            "db_path": self._storage._db_path,
        }

    def verify_integrity(self, key: str) -> bool:
        """Verify the SHA256 hash integrity of a memory.

        Args:
            key: The memory key.

        Returns:
            True if the stored hash matches recomputed hash.

        Raises:
            MemoryNotFoundError: If the key does not exist.
        """
        entry = self.retrieve_memory(key)
        expected = self._generate_hash(entry.value)
        ok = entry.hash == expected
        if not ok:
            logger.warning("Integrity verification FAILED for %s", key)
        return ok

    def close(self) -> None:
        """Close database connections."""
        self._storage.close()
        logger.info("MemoryManager closed")

    # -- private helpers ------------------------------------------------------

    @staticmethod
    def _generate_hash(value: str) -> str:
        """Generate SHA256 hash of a string value."""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _calculate_age(timestamp: str) -> float:
        """Calculate age of a memory in seconds from an ISO timestamp."""
        try:
            stored = datetime.fromisoformat(timestamp)
            if stored.tzinfo is None:
                stored = stored.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - stored).total_seconds()
        except (ValueError, TypeError) as exc:
            logger.warning("Could not parse timestamp %r: %s", timestamp, exc)
            return 0.0


# ---------------------------------------------------------------------------
# JSON -> SQLite Migration
# ---------------------------------------------------------------------------


def migrate_from_json(
    json_path: str = "memories.json",
    db_path: str = "memories.db",
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Migrate memories from the legacy JSON file to the new SQLite database.

    Args:
        json_path: Path to the legacy JSON file.
        db_path: Path to the target SQLite database.
        dry_run: If True, validate but don't write.

    Returns:
        Migration report dict.
    """
    report: Dict[str, Any] = {
        "source": json_path,
        "target": db_path,
        "dry_run": dry_run,
        "total_found": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": [],
    }

    json_file = Path(json_path)
    if not json_file.exists():
        report["errors"].append(f"Source file not found: {json_path}")
        logger.error("Migration source not found: %s", json_path)
        return report

    try:
        with open(json_file, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        report["errors"].append(f"Failed to read source: {exc}")
        logger.error("Migration read error: %s", exc)
        return report

    if not isinstance(data, dict):
        report["errors"].append("Unexpected JSON structure: expected a dict")
        return report

    report["total_found"] = len(data)
    logger.info("Migration: found %d entries in %s", len(data), json_path)

    if dry_run:
        for key, entry in data.items():
            try:
                _validate_key(key)
                _validate_value(str(entry.get("value", "")))
                _validate_tags(entry.get("tags"))
                report["migrated"] += 1
            except MemoryValidationError as exc:
                report["skipped"] += 1
                report["errors"].append(f"Validation failed for {key!r}: {exc}")
        return report

    manager = MemoryManager(db_path=db_path)
    try:
        for key, entry in data.items():
            try:
                value = str(entry.get("value", ""))
                tags = entry.get("tags", [])
                manager.store_memory(key, value, tags)
                report["migrated"] += 1
            except (MemoryValidationError, MemoryStorageError) as exc:
                report["skipped"] += 1
                report["errors"].append(f"Failed to migrate {key!r}: {exc}")
                logger.warning("Migration skipped %s: %s", key, exc)
    finally:
        manager.close()

    logger.info(
        "Migration complete: %d migrated, %d skipped out of %d",
        report["migrated"],
        report["skipped"],
        report["total_found"],
    )
    return report


# ---------------------------------------------------------------------------
# Demo / CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Demonstrate the production-grade Memory Manager."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("\n=== Memory Manager Agent v2.0 - Production Grade ===")
    print(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    db_path = "demo_memories.db"
    manager = MemoryManager(db_path=db_path)

    try:
        # Store memories
        print("\n[STORING] Adding sample memories...")
        manager.store_memory("task_1", "Complete ML model training", ["urgent", "ml"])
        manager.store_memory("task_2", "Review code changes", ["code", "review"])
        manager.store_memory("note_1", "Meeting scheduled for 3 PM", ["meeting", "schedule"])
        print("Stored 3 memories")

        # Retrieve
        print("\n[RETRIEVING] Fetching specific memory...")
        entry = manager.retrieve_memory("task_1")
        print(f"Retrieved: {entry.value}")
        print(f"Tags: {entry.tags}")
        print(f"Integrity hash: {entry.hash[:16]}...")

        # Search (FTS)
        print("\n[SEARCHING] Full-text search for 'code'...")
        results = manager.search_memories(query="code")
        print(f"Found {len(results)} results")
        for r in results:
            print(f"  - {r.key}: {r.value}")

        # Search by tag
        print("\n[TAG SEARCH] Filtering by tag 'urgent'...")
        results = manager.search_memories(tag="urgent")
        print(f"Found {len(results)} results")

        # Analyze with integrity check
        print("\n[ANALYZING] Memory analysis with integrity verification...")
        analysis = manager.analyze_memory("task_1")
        print(f"Analysis: {json.dumps(analysis, indent=2)}")

        # Verify integrity
        print("\n[INTEGRITY] Verifying hash integrity...")
        ok = manager.verify_integrity("task_1")
        print(f"Integrity check: {'PASSED' if ok else 'FAILED'}")

        # Statistics
        print("\n[STATS] Memory Manager Statistics...")
        stats = manager.get_statistics()
        print(f"Total Memories: {stats['total_memories']}")
        print(f"Total Tags: {stats['total_tags']}")
        print(f"Tags breakdown: {stats['tags']}")

        # Delete
        print("\n[DELETE] Removing task_2...")
        deleted = manager.delete_memory("task_2")
        print(f"Deleted: {deleted}")

        # List with pagination
        print("\n[LIST] Remaining memories:")
        keys = manager.list_memories(limit=10)
        for k in keys:
            print(f"  - {k}")

    finally:
        manager.close()
        # Clean up demo database
        Path(db_path).unlink(missing_ok=True)

    print("\n=== Memory Manager Agent Execution Complete ===")
    print(f"Finished at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")


if __name__ == "__main__":
    main()
