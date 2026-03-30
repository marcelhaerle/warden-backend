import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Any

import asyncpg
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("warden-backend")


SCAN_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id BIGSERIAL PRIMARY KEY,
    agent_version TEXT NOT NULL,
    hostname TEXT NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    success BOOLEAN NOT NULL,
    error TEXT,
    raw_scan_data JSONB NOT NULL,
    result_count INTEGER NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

SCAN_RUNS_JSONB_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS scan_runs_raw_data_gin_idx
ON scan_runs USING GIN (raw_scan_data)
"""

SCAN_RUNS_HOST_REPORTED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS scan_runs_hostname_reported_at_idx
ON scan_runs (hostname, reported_at DESC)
"""

SCAN_RUNS_SUCCESS_REPORTED_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS scan_runs_success_reported_at_idx
ON scan_runs (success, reported_at DESC)
"""


class AgentPayload(BaseModel):
    agent_version: str
    hostname: str
    timestamp: str
    success: bool
    error: str | None = None
    scan_data: dict[str, str]


class ScanRunSummary(BaseModel):
    id: int
    agent_version: str
    hostname: str
    reported_at: datetime
    success: bool
    error: str | None = None
    result_count: int
    hardening_index: int | None = None
    warnings: int | None = None
    suggestions: int | None = None


class ScanRunsResponse(BaseModel):
    total: int
    count: int
    limit: int
    offset: int
    items: list[ScanRunSummary]


class ScanRunDetail(ScanRunSummary):
    raw_scan_data: dict[str, Any]
    received_at: datetime


redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)


def parse_reported_at(timestamp: str) -> datetime:
    normalized = timestamp.replace("Z", "+00:00")
    reported_at = datetime.fromisoformat(normalized)
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)
    return reported_at


async def init_connection(conn):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_postgres_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "warden"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        init=init_connection,
    )


async def ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(SCAN_RUNS_TABLE_SQL)
        await connection.execute(SCAN_RUNS_JSONB_INDEX_SQL)
        await connection.execute(SCAN_RUNS_HOST_REPORTED_INDEX_SQL)
        await connection.execute(SCAN_RUNS_SUCCESS_REPORTED_INDEX_SQL)


def build_metadata_filters(
    hostname: str | None,
    success: bool | None,
    agent_version: str | None,
    reported_from: datetime | None,
    reported_to: datetime | None,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if hostname:
        clauses.append(f"hostname ILIKE ${len(params) + 1}")
        params.append(f"%{hostname}%")

    if success is not None:
        clauses.append(f"success = ${len(params) + 1}")
        params.append(success)

    if agent_version:
        clauses.append(f"agent_version = ${len(params) + 1}")
        params.append(agent_version)

    if reported_from is not None:
        clauses.append(f"reported_at >= ${len(params) + 1}")
        params.append(reported_from)

    if reported_to is not None:
        clauses.append(f"reported_at <= ${len(params) + 1}")
        params.append(reported_to)

    return clauses, params


def parse_json_contains(json_contains: str) -> str:
    try:
        parsed = json.loads(json_contains)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="json_contains must be valid JSON",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400,
            detail="json_contains must be a JSON object",
        )

    return json.dumps(parsed)


async def fetch_scan_runs(
    app: FastAPI,
    clauses: list[str],
    params: list[Any],
    limit: int,
    offset: int,
) -> ScanRunsResponse:
    where_clause = " AND ".join(clauses) if clauses else "TRUE"
    pool = app.state.pool

    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM scan_runs WHERE {where_clause}",
        *params,
    )

    rows = await pool.fetch(
        f"""
        SELECT
            id,
            agent_version,
            hostname,
            reported_at,
            success,
            error,
            result_count,
            received_at,
            CAST(raw_scan_data->>'hardening_index' AS INTEGER) AS hardening_index,
            CAST(raw_scan_data->>'warnings' AS INTEGER) AS warnings,
            CAST(raw_scan_data->>'suggestions' AS INTEGER) AS suggestions
        FROM scan_runs
        WHERE {where_clause}
        ORDER BY reported_at DESC, id DESC
        LIMIT ${len(params) + 1}
        OFFSET ${len(params) + 2}
        """,
        *params,
        limit,
        offset,
    )

    items = [ScanRunSummary.model_validate(dict(row)) for row in rows]
    return ScanRunsResponse(
        total=total,
        count=len(items),
        limit=limit,
        offset=offset,
        items=items,
    )


async def save_scan_results(pool: asyncpg.Pool, payload: AgentPayload) -> int:
    reported_at = parse_reported_at(payload.timestamp)

    async with pool.acquire() as connection:
        scan_run_id = await connection.fetchval(
            """
            INSERT INTO scan_runs (
                agent_version,
                hostname,
                reported_at,
                success,
                error,
                raw_scan_data,
                result_count
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            payload.agent_version,
            payload.hostname,
            reported_at,
            payload.success,
            payload.error,
            payload.scan_data,
            len(payload.scan_data),
        )
    return scan_run_id


async def redis_worker(app: FastAPI):
    """Background task: continuously listens to the Redis queue."""
    logger.info("Redis worker started. Waiting for data in 'warden_queue'...")
    try:
        while True:
            result = await redis_client.brpop("warden_queue", timeout=0)
            if result:
                _, raw_data = result
                try:
                    parsed_json = json.loads(raw_data)
                    payload = AgentPayload(**parsed_json)

                    pool = app.state.pool
                    scan_run_id = await save_scan_results(pool, payload)
                    logger.info(f"Scan Run {scan_run_id} from {payload.hostname} saved.")

                except Exception as e:
                    logger.error(f"Error processing payload: {e}")
                    # If the DB is down, put the data back in the queue.
                    logger.warning("Putting payload back into Redis queue (Retry).")
                    await redis_client.lpush("warden_queue", raw_data)
                    # Prevents an endless loop in case of a permanent DB failure
                    await asyncio.sleep(5)

    except asyncio.CancelledError:
        logger.info("Redis worker is shutting down cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_postgres_pool()
    await ensure_schema(app.state.pool)
    logger.info("PostgreSQL connected and schema initialized.")

    task = asyncio.create_task(redis_worker(app))
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    await redis_client.close()
    await app.state.pool.close()


app = FastAPI(title="Warden API", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "Warden backend is running", "worker": "active"}


@app.get("/api/scans", response_model=ScanRunsResponse)
async def list_scan_results(
    hostname: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    agent_version: str | None = Query(default=None),
    reported_from: datetime | None = Query(default=None),
    reported_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    clauses, params = build_metadata_filters(
        hostname=hostname,
        success=success,
        agent_version=agent_version,
        reported_from=reported_from,
        reported_to=reported_to,
    )
    return await fetch_scan_runs(
        app=app,
        clauses=clauses,
        params=params,
        limit=limit,
        offset=offset,
    )


@app.get("/api/scans/{scan_id}", response_model=ScanRunDetail)
async def get_scan_detail(scan_id: int):
    pool = app.state.pool

    row = await pool.fetchrow("SELECT * FROM scan_runs WHERE id = $1", scan_id)

    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanRunDetail.model_validate(dict(row))


@app.get("/api/scans/search", response_model=ScanRunsResponse)
async def search_scan_results(
    hostname: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    agent_version: str | None = Query(default=None),
    reported_from: datetime | None = Query(default=None),
    reported_to: datetime | None = Query(default=None),
    json_key: str | None = Query(default=None),
    json_value: str | None = Query(default=None),
    json_contains: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if (json_key is None) != (json_value is None):
        raise HTTPException(
            status_code=400,
            detail="json_key and json_value must be provided together",
        )

    if json_key is None and json_contains is None:
        raise HTTPException(
            status_code=400,
            detail="Provide json_key/json_value or json_contains",
        )

    clauses, params = build_metadata_filters(
        hostname=hostname,
        success=success,
        agent_version=agent_version,
        reported_from=reported_from,
        reported_to=reported_to,
    )

    if json_key is not None and json_value is not None:
        key_param = len(params) + 1
        value_param = len(params) + 2
        clauses.append(f"jsonb_extract_path_text(raw_scan_data, ${key_param}) = ${value_param}")
        params.extend([json_key, json_value])

    if json_contains is not None:
        contains_param = len(params) + 1
        clauses.append(f"raw_scan_data @> ${contains_param}::jsonb")
        params.append(parse_json_contains(json_contains))

    return await fetch_scan_runs(
        app=app,
        clauses=clauses,
        params=params,
        limit=limit,
        offset=offset,
    )
