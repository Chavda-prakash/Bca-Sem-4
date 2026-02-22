# Memory Manager Agent - Production Grade

## Overview

A production-grade **Memory Manager Agent** built for TinyFish platform with SQLite-backed persistent storage, full-text search, concurrency handling, input validation, and comprehensive test coverage.

**v2.0** is a complete rewrite of the original JSON-based prototype, addressing all architectural, security, performance, and reliability issues.

## Architecture

```
MemoryManager (public API, thread-safe)
    |
    +-- SQLiteStorage (storage backend)
    |       |-- memories table (key, value, timestamp, hash, updated_at)
    |       |-- memory_tags table (key, tag) with FK cascade delete
    |       |-- memories_fts (FTS5 virtual table for full-text search)
    |       |-- Triggers (auto-sync FTS index on insert/update/delete)
    |       |-- WAL mode + busy_timeout for concurrent access
    |
    +-- Validation layer (_validate_key, _validate_value, _validate_tags)
    +-- Custom exception hierarchy (MemoryManagerError -> NotFound/Validation/Storage)
    +-- MemoryEntry data class (typed, slotted)
    +-- Structured logging (Python logging module)
```

## Features

**Core:**
- Store, retrieve, update, and delete memories with metadata
- Full-text search via SQLite FTS5 (ranked results)
- Tag-based filtering with indexed lookups
- Pagination on list and search operations
- SHA256 integrity hashing with verification

**Production:**
- SQLite with WAL mode for concurrent reads
- Thread-safe operations via `threading.Lock`
- Thread-local database connections
- Atomic transactions with rollback on failure
- Input validation with size limits and type checking
- Custom exception hierarchy (no silent failures)
- Structured logging via Python `logging` module
- Schema versioning for future migrations
- JSON-to-SQLite migration tool with dry-run support

## Installation

```bash
git clone https://github.com/Chavda-prakash/Bca-Sem-4.git
cd Bca-Sem-4

# Run the demo
python memory_manager.py

# Run the test suite (74 tests)
python -m unittest test_memory_manager.py -v
```

## Usage

### Basic Example

```python
from memory_manager import MemoryManager

# Initialize (creates SQLite DB automatically)
manager = MemoryManager(db_path="memories.db")

# Store a memory
entry = manager.store_memory("task_1", "Complete project", ["urgent", "work"])
print(entry.hash)  # SHA256 hash

# Retrieve a memory (returns MemoryEntry object)
entry = manager.retrieve_memory("task_1")
print(entry.value)  # "Complete project"
print(entry.tags)   # ["urgent", "work"]

# Full-text search
results = manager.search_memories(query="project")
print(f"Found {len(results)} results")

# Search by tag
results = manager.search_memories(tag="urgent")

# Combined search (FTS + tag filter)
results = manager.search_memories(query="project", tag="work")

# List with pagination
keys = manager.list_memories(limit=10, offset=0)

# Verify data integrity
ok = manager.verify_integrity("task_1")

# Get statistics
stats = manager.get_statistics()
print(stats)

# Always close when done
manager.close()
```

### Migration from JSON (v1.0)

```python
from memory_manager import migrate_from_json

# Dry run first (validates without writing)
report = migrate_from_json("memories.json", "memories.db", dry_run=True)
print(report)

# Actual migration
report = migrate_from_json("memories.json", "memories.db")
print(f"Migrated: {report['migrated']}, Skipped: {report['skipped']}")
```

## API Reference

### MemoryManager Methods

| Method | Description | Returns | Raises |
|--------|-------------|---------|--------|
| `store_memory(key, value, tags)` | Store or update a memory | `MemoryEntry` | `MemoryValidationError`, `MemoryStorageError` |
| `retrieve_memory(key)` | Fetch memory by key | `MemoryEntry` | `MemoryNotFoundError` |
| `search_memories(query, tag, limit, offset)` | Full-text + tag search | `List[MemoryEntry]` | `MemoryValidationError` |
| `analyze_memory(key)` | Analyze with integrity check | `Dict[str, Any]` | `MemoryNotFoundError` |
| `delete_memory(key)` | Remove a memory | `bool` | `MemoryValidationError` |
| `list_memories(tag, limit, offset)` | List keys with pagination | `List[str]` | `MemoryValidationError` |
| `get_statistics()` | Storage statistics | `Dict[str, Any]` | - |
| `verify_integrity(key)` | Verify SHA256 hash | `bool` | `MemoryNotFoundError` |
| `close()` | Close DB connections | `None` | - |

### Exception Hierarchy

```
MemoryManagerError (base)
  +-- MemoryNotFoundError
  +-- MemoryValidationError
  +-- MemoryStorageError
```

### Validation Limits

| Parameter | Limit |
|-----------|-------|
| Key length | 256 characters |
| Value size | 1 MB |
| Tag length | 128 characters |
| Tags per memory | 50 |
| Search limit | 1-1000 |

## Storage Format

SQLite database with three tables:

```sql
-- Main storage
CREATE TABLE memories (
    key TEXT PRIMARY KEY, value TEXT, timestamp TEXT,
    hash TEXT, updated_at TEXT
);

-- Tag index (cascade delete)
CREATE TABLE memory_tags (
    key TEXT, tag TEXT, PRIMARY KEY (key, tag),
    FOREIGN KEY (key) REFERENCES memories(key) ON DELETE CASCADE
);

-- Full-text search (auto-synced via triggers)
CREATE VIRTUAL TABLE memories_fts USING fts5(key, value);
```

## Migration Strategy (v1.0 -> v2.0)

1. **Backup** your existing `memories.json`
2. **Dry run**: `migrate_from_json("memories.json", "memories.db", dry_run=True)`
3. **Review** the report for any validation errors
4. **Migrate**: `migrate_from_json("memories.json", "memories.db")`
5. **Verify**: Open the new DB and spot-check entries
6. **Update** your code to use `MemoryManager(db_path="memories.db")` instead of `MemoryManager(storage_file="memories.json")`

The migration function handles:
- Value type coercion (non-string values converted to string)
- Tag normalization (lowercase, trimmed)
- Validation of all entries (invalid entries are skipped with error report)
- Idempotent (safe to run multiple times)

## Testing

74 tests covering 10 categories:

```bash
python -m unittest test_memory_manager.py -v
```

| Category | Tests | Coverage |
|----------|-------|----------|
| CRUD Operations | 16 | Store, retrieve, delete, list |
| Input Validation | 18 | Keys, values, tags, limits |
| Full-Text Search | 6 | FTS5, tag filter, combined, pagination |
| Integrity & Analysis | 5 | Hash verification, analysis fields |
| Statistics | 3 | Empty, after store, after delete |
| MemoryEntry | 3 | to_dict, repr, defaults |
| Concurrency | 2 | Parallel stores, mixed read/write |
| Migration | 6 | Success, dry-run, errors, edge cases |
| SQLiteStorage | 5 | Low-level insert, get, delete, count |
| Edge Cases | 7 | Max key, unicode, special chars, reopen |

## Performance

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Store/Retrieve/Delete | O(1) | Primary key lookup |
| Full-text search | O(log n) | FTS5 inverted index |
| Tag filter | O(log n) | B-tree index on tag column |
| List all | O(k) | k = limit parameter |
| Concurrent reads | Parallel | WAL mode allows concurrent readers |

## Version History

- **v2.0.0** - Production-grade rewrite (SQLite, FTS5, concurrency, validation, tests)
- **v1.0.0** - Initial prototype (JSON file storage)

## Author

**Chavda-prakash** - BCA Semester 4

## License

MIT License - Feel free to use and modify

## Testing with CodeRabbit

This project is integrated with CodeRabbit for continuous code analysis and quality metrics.

- Repository: https://github.com/Chavda-prakash/Bca-Sem-4
- Integration: CodeRabbit AI Code Reviews
- Status: Active monitoring and analysis

## Contributing

Feel free to submit issues and enhancement requests!

---

**Last Updated**: 2026-02-22
**Status**: Production Ready (v2.0)
