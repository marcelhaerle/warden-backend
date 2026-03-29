import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import asyncpg
from fastapi import FastAPI
from pydantic import BaseModel
import redis.asyncio as redis

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

SCAN_RUNS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS scan_runs_hostname_reported_at_idx
ON scan_runs (hostname, reported_at DESC)
"""

SCAN_RESULTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scan_results (
    id BIGSERIAL PRIMARY KEY,
    scan_run_id BIGINT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    result_key TEXT NOT NULL,
    result_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT scan_results_scan_run_id_result_key_key UNIQUE (scan_run_id, result_key)
)
"""

SCAN_RESULTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS scan_results_result_key_idx
ON scan_results (result_key)
"""


class AgentPayload(BaseModel):
    agent_version: str
    hostname: str
    timestamp: str
    success: bool
    error: str | None = None
    scan_data: dict[str, str]


# Initialize Redis connection (asynchronous) from environment variables
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    decode_responses=True,
)

postgres_pool: asyncpg.Pool | None = None


def parse_reported_at(timestamp: str) -> datetime:
    normalized_timestamp = timestamp.replace("Z", "+00:00")
    reported_at = datetime.fromisoformat(normalized_timestamp)
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)
    return reported_at


async def create_postgres_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "warden"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


async def ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(SCAN_RUNS_TABLE_SQL)
        await connection.execute(SCAN_RUNS_INDEX_SQL)
        await connection.execute(SCAN_RESULTS_TABLE_SQL)
        await connection.execute(SCAN_RESULTS_INDEX_SQL)


async def save_scan_results(payload: AgentPayload) -> int:
    if postgres_pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized")

    reported_at = parse_reported_at(payload.timestamp)
    scan_data_json = json.dumps(payload.scan_data)

    async with postgres_pool.acquire() as connection:
        async with connection.transaction():
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
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                RETURNING id
                """,
                payload.agent_version,
                payload.hostname,
                reported_at,
                payload.success,
                payload.error,
                scan_data_json,
                len(payload.scan_data),
            )

            if payload.scan_data:
                await connection.executemany(
                    """
                    INSERT INTO scan_results (scan_run_id, result_key, result_value)
                    VALUES ($1, $2, $3)
                    """,
                    [
                        (scan_run_id, result_key, result_value)
                        for result_key, result_value in payload.scan_data.items()
                    ],
                )

    return scan_run_id


async def redis_worker():
    """Background task: continuously listens to the Redis queue."""
    logger.info("Redis worker started. Waiting for data in 'warden_queue'...")
    try:
        while True:
            # brpop blocks without CPU load until an item arrives in the list
            # (timeout=0 means wait indefinitely)
            result = await redis_client.brpop("warden_queue", timeout=0)
            if result:
                queue_name, raw_data = result
                try:
                    # Parse JSON and validate it directly with Pydantic
                    parsed_json = json.loads(raw_data)
                    payload = AgentPayload(**parsed_json)

                    logger.info(
                        f"Received new agent package from: {payload.hostname}")
                    logger.info(
                        f"Timestamp: {payload.timestamp} | Successful: {payload.success}")
                    logger.info(
                        f"Found scan metrics: {len(payload.scan_data)}")

                    scan_run_id = await save_scan_results(payload)
                    logger.info(
                        f"Stored scan run {scan_run_id} and {len(payload.scan_data)} result entries in PostgreSQL")

                except Exception as e:
                    logger.error(f"Error while processing payload: {e}")

    except asyncio.CancelledError:
        logger.info("Redis worker is shutting down cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global postgres_pool

    # Runs when Uvicorn starts
    postgres_pool = await create_postgres_pool()
    await ensure_schema(postgres_pool)
    logger.info("PostgreSQL connection established and schema is ready.")

    task = asyncio.create_task(redis_worker())
    yield
    # Runs during shutdown (Ctrl+C)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    await redis_client.close()

    if postgres_pool is not None:
        await postgres_pool.close()
        postgres_pool = None

app = FastAPI(title="Warden API", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "Warden backend is running", "worker": "active"}
