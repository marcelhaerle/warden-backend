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

SCAN_RUNS_JSONB_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS scan_runs_raw_data_gin_idx
ON scan_runs USING GIN (raw_scan_data)
"""


class AgentPayload(BaseModel):
    agent_version: str
    hostname: str
    timestamp: str
    success: bool
    error: str | None = None
    scan_data: dict[str, str]


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
        await connection.execute(SCAN_RUNS_JSONB_INDEX_SQL)


async def save_scan_results(pool: asyncpg.Pool, payload: AgentPayload) -> int:
    reported_at = parse_reported_at(payload.timestamp)
    scan_data_json = json.dumps(payload.scan_data)

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
                    logger.info(
                        f"Scan Run {scan_run_id} from {payload.hostname} saved.")

                except Exception as e:
                    logger.error(f"Error processing payload: {e}")
                    # If the DB is down, put the data back in the queue.
                    logger.warning(
                        "Putting payload back into Redis queue (Retry).")
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
