#!/usr/bin/env python3
"""
REST API layer for the Memory Manager engine.

FastAPI application providing CRUD, search, pagination, error handling,
rate limiting, and authentication placeholder for the SQLite memory system.

Usage:
    pip install fastapi uvicorn slowapi
    uvicorn api:app --reload --port 8000

Endpoints:
    POST   /api/v1/memories          - Store a memory
    GET    /api/v1/memories/{key}     - Retrieve a memory
    DELETE /api/v1/memories/{key}     - Delete a memory
    GET    /api/v1/memories           - List memories (paginated)
    GET    /api/v1/search             - Search memories (FTS5 + tag)
    GET    /api/v1/memories/{key}/analyze  - Analyze a memory
    GET    /api/v1/memories/{key}/verify   - Verify integrity
    GET    /api/v1/statistics         - Get statistics
    GET    /api/v1/health             - Health check
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from memory_manager import (
    MemoryManager,
    MemoryManagerError,
    MemoryNotFoundError,
    MemoryStorageError,
    MemoryValidationError,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("memory_api")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = os.environ.get("MEMORY_DB_PATH", "memories.db")
API_KEY = os.environ.get("MEMORY_API_KEY", "")  # Empty = auth disabled
RATE_LIMIT = os.environ.get("MEMORY_RATE_LIMIT", "60/minute")

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Memory Manager API",
    description="Production-grade REST API for the SQLite Memory Manager engine with FTS5 search, pagination, rate limiting, and auth placeholder.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
    )


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Singleton MemoryManager
# ---------------------------------------------------------------------------
_manager: Optional[MemoryManager] = None


def get_manager() -> MemoryManager:
    """Lazy-init singleton MemoryManager."""
    global _manager
    if _manager is None:
        _manager = MemoryManager(db_path=DB_PATH)
        logger.info("MemoryManager initialized (db=%s)", DB_PATH)
    return _manager


@app.on_event("shutdown")
def shutdown_manager() -> None:
    global _manager
    if _manager is not None:
        _manager.close()
        _manager = None
        logger.info("MemoryManager closed on shutdown")


# ---------------------------------------------------------------------------
# Auth placeholder
# ---------------------------------------------------------------------------

def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Placeholder authentication via X-API-Key header.

    If MEMORY_API_KEY env var is set, requests must include a matching
    X-API-Key header. If the env var is empty, auth is disabled.
    """
    if not API_KEY:
        return  # Auth disabled
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class StoreMemoryRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=256, description="Unique memory key")
    value: str = Field(..., description="Memory content")
    tags: Optional[List[str]] = Field(None, max_length=50, description="Optional tags")


class MemoryResponse(BaseModel):
    key: str
    value: str
    timestamp: str
    tags: List[str]
    hash: str
    updated_at: str


class AnalysisResponse(BaseModel):
    key: str
    value: str
    stored_at: str
    updated_at: str
    tags: List[str]
    hash: str
    integrity_verified: bool
    age_seconds: float


class StatsResponse(BaseModel):
    total_memories: int
    total_tags: int
    tags: List[Dict[str, Any]]
    storage_backend: str
    db_path: str


class PaginatedKeysResponse(BaseModel):
    keys: List[str]
    limit: int
    offset: int
    total: Optional[int] = None


class SearchResponse(BaseModel):
    results: List[MemoryResponse]
    count: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    version: str
    db_path: str
    uptime_seconds: float


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Startup time tracking
# ---------------------------------------------------------------------------
_start_time = time.time()


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------

def _map_exception(exc: MemoryManagerError) -> HTTPException:
    """Map domain exceptions to HTTP status codes."""
    if isinstance(exc, MemoryNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, MemoryValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, MemoryStorageError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
@limiter.limit("120/minute")
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        db_path=DB_PATH,
        uptime_seconds=round(time.time() - _start_time, 2),
    )


@app.post(
    "/api/v1/memories",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Memories"],
    responses={422: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def store_memory(
    request: Request,
    body: StoreMemoryRequest,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> MemoryResponse:
    """Store or update a memory entry."""
    try:
        entry = manager.store_memory(body.key, body.value, body.tags)
        return MemoryResponse(**entry.to_dict())
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.get(
    "/api/v1/memories/{key}",
    response_model=MemoryResponse,
    tags=["Memories"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def retrieve_memory(
    request: Request,
    key: str,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> MemoryResponse:
    """Retrieve a memory by key."""
    try:
        entry = manager.retrieve_memory(key)
        return MemoryResponse(**entry.to_dict())
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.delete(
    "/api/v1/memories/{key}",
    tags=["Memories"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def delete_memory(
    request: Request,
    key: str,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> Dict[str, Any]:
    """Delete a memory by key."""
    try:
        deleted = manager.delete_memory(key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Memory not found: {key!r}")
        return {"deleted": True, "key": key}
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.get(
    "/api/v1/memories",
    response_model=PaginatedKeysResponse,
    tags=["Memories"],
    responses={422: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def list_memories(
    request: Request,
    tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> PaginatedKeysResponse:
    """List memory keys with optional tag filter and pagination."""
    try:
        keys = manager.list_memories(tag=tag, limit=limit, offset=offset)
        total = manager.count_memories(tag=tag)
        return PaginatedKeysResponse(keys=keys, limit=limit, offset=offset, total=total)
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.get(
    "/api/v1/search",
    response_model=SearchResponse,
    tags=["Search"],
    responses={422: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def search_memories(
    request: Request,
    query: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> SearchResponse:
    """Search memories using full-text search (FTS5) and/or tag filtering."""
    try:
        results = manager.search_memories(query=query, tag=tag, limit=limit, offset=offset)
        return SearchResponse(
            results=[MemoryResponse(**e.to_dict()) for e in results],
            count=len(results),
            limit=limit,
            offset=offset,
        )
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.get(
    "/api/v1/memories/{key}/analyze",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def analyze_memory(
    request: Request,
    key: str,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> AnalysisResponse:
    """Analyze a memory entry with integrity verification."""
    try:
        analysis = manager.analyze_memory(key)
        return AnalysisResponse(**analysis)
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.get(
    "/api/v1/memories/{key}/verify",
    tags=["Analysis"],
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit(RATE_LIMIT)
async def verify_integrity(
    request: Request,
    key: str,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> Dict[str, Any]:
    """Verify the SHA256 integrity of a memory."""
    try:
        ok = manager.verify_integrity(key)
        return {"key": key, "integrity_verified": ok}
    except MemoryManagerError as exc:
        raise _map_exception(exc)


@app.get(
    "/api/v1/statistics",
    response_model=StatsResponse,
    tags=["Statistics"],
)
@limiter.limit(RATE_LIMIT)
async def get_statistics(
    request: Request,
    _: None = Depends(verify_api_key),
    manager: MemoryManager = Depends(get_manager),
) -> StatsResponse:
    """Get memory store statistics."""
    stats = manager.get_statistics()
    return StatsResponse(**stats)
