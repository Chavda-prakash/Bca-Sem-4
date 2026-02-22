#!/usr/bin/env python3
"""
Locust-based load testing script for the Memory Manager FastAPI endpoints.
Simulates 100 concurrent users with mixed workload:
  - 40% reads  (GET /api/v1/memories/{key})
  - 30% search (GET /api/v1/search)
  - 20% writes (POST /api/v1/memories)
  - 10% deletes (DELETE /api/v1/memories/{key})
Usage (headless, for automated collection):
    MEMORY_RATE_LIMIT="10000/minute" uvicorn api:app --port 8000 &
    locust -f loadtest.py --headless -u 100 -r 10 --run-time 60s \
           --host http://127.0.0.1:8000 --csv results/loadtest
Usage (web UI):
    locust -f loadtest.py --host http://127.0.0.1:8000
"""
import random
import string
import uuid
from locust import HttpUser, between, task
def _random_string(length: int = 64) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))
# Pre-generated pool of keys so reads/deletes target real data
_SEED_KEYS: list[str] = [f"loadtest-key-{i}" for i in range(500)]
_SEARCH_TERMS: list[str] = [
    "performance",
    "memory",
    "data",
    "test",
    "load",
    "system",
    "cache",
    "query",
    "store",
    "index",
]
_TAGS: list[str] = [
    "benchmark",
    "loadtest",
    "perf",
    "stress",
    "validation",
    "alpha",
    "beta",
    "gamma",
]
class MemoryAPIUser(HttpUser):
    """Simulates a realistic mixed-workload user hitting the Memory Manager API."""
    # Wait 50-200ms between tasks to model realistic client behaviour
    wait_time = between(0.05, 0.2)
    def on_start(self) -> None:
        """Seed a handful of memories so read/search/delete have data to hit."""
        for key in random.sample(_SEED_KEYS, min(20, len(_SEED_KEYS))):
            tags = random.sample(_TAGS, k=random.randint(1, 3))
            self.client.post(
                "/api/v1/memories",
                json={
                    "key": key,
                    "value": f"Seed value about {random.choice(_SEARCH_TERMS)} - {_random_string(128)}",
                    "tags": tags,
                },
                name="/api/v1/memories [seed]",
            )
    # ------------------------------------------------------------------
    # 40 % reads
    # ------------------------------------------------------------------
    @task(40)
    def read_memory(self) -> None:
        key = random.choice(_SEED_KEYS)
        with self.client.get(
            f"/api/v1/memories/{key}",
            name="/api/v1/memories/{key} [GET]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
    # ------------------------------------------------------------------
    # 30 % searches
    # ------------------------------------------------------------------
    @task(15)
    def search_fts(self) -> None:
        """Full-text search query."""
        term = random.choice(_SEARCH_TERMS)
        self.client.get(
            f"/api/v1/search?query={term}&limit=20",
            name="/api/v1/search [FTS]",
        )
    @task(10)
    def search_tag(self) -> None:
        """Tag-only search."""
        tag = random.choice(_TAGS)
        self.client.get(
            f"/api/v1/search?tag={tag}&limit=20",
            name="/api/v1/search [tag]",
        )
    @task(5)
    def search_combined(self) -> None:
        """FTS + tag combined search."""
        term = random.choice(_SEARCH_TERMS)
        tag = random.choice(_TAGS)
        self.client.get(
            f"/api/v1/search?query={term}&tag={tag}&limit=20",
            name="/api/v1/search [combined]",
        )
    # ------------------------------------------------------------------
    # 20 % writes
    # ------------------------------------------------------------------
    @task(15)
    def write_existing_key(self) -> None:
        """Update an existing seeded key."""
        key = random.choice(_SEED_KEYS)
        tags = random.sample(_TAGS, k=random.randint(1, 3))
        self.client.post(
            "/api/v1/memories",
            json={
                "key": key,
                "value": f"Updated value about {random.choice(_SEARCH_TERMS)} - {_random_string(128)}",
                "tags": tags,
            },
            name="/api/v1/memories [POST update]",
        )
    @task(5)
    def write_new_key(self) -> None:
        """Insert a brand-new key."""
        key = f"loadtest-new-{uuid.uuid4().hex[:12]}"
        tags = random.sample(_TAGS, k=random.randint(1, 3))
        self.client.post(
            "/api/v1/memories",
            json={
                "key": key,
                "value": f"New value about {random.choice(_SEARCH_TERMS)} - {_random_string(256)}",
                "tags": tags,
            },
            name="/api/v1/memories [POST new]",
        )
    # ------------------------------------------------------------------
    # 10 % deletes
    # ------------------------------------------------------------------
    @task(10)
    def delete_memory(self) -> None:
        key = random.choice(_SEED_KEYS)
        with self.client.delete(
            f"/api/v1/memories/{key}",
            name="/api/v1/memories/{key} [DELETE]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
    # ------------------------------------------------------------------
    # Bonus: light-weight list / stats to round out traffic mix
    # ------------------------------------------------------------------
    @task(3)
    def list_memories(self) -> None:
        self.client.get(
            "/api/v1/memories?limit=50&offset=0",
            name="/api/v1/memories [LIST]",
        )
    @task(2)
    def get_statistics(self) -> None:
        self.client.get(
            "/api/v1/statistics",
            name="/api/v1/statistics",
        )
