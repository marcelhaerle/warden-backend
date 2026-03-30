import json
from datetime import datetime, timezone

import asyncpg

from app.config import settings

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


def parse_reported_at(timestamp: str) -> datetime:
    normalized = timestamp.replace("Z", "+00:00")
    reported_at = datetime.fromisoformat(normalized)
    if reported_at.tzinfo is None:
        reported_at = reported_at.replace(tzinfo=timezone.utc)
    return reported_at


async def init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_postgres_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=settings.postgres.host,
        port=settings.postgres.port,
        database=settings.postgres.database,
        user=settings.postgres.user,
        password=settings.postgres.password,
        init=init_connection,
    )


async def ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(SCAN_RUNS_TABLE_SQL)
        await connection.execute(SCAN_RUNS_JSONB_INDEX_SQL)
        await connection.execute(SCAN_RUNS_HOST_REPORTED_INDEX_SQL)
        await connection.execute(SCAN_RUNS_SUCCESS_REPORTED_INDEX_SQL)
