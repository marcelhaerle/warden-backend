from typing import Any

import asyncpg

from app.core.database import parse_reported_at
from app.models import AgentPayload


async def count_scan_runs(pool: asyncpg.Pool, where_clause: str, params: list[Any]) -> int:
    return await pool.fetchval(f"SELECT COUNT(*) FROM scan_runs WHERE {where_clause}", *params)


async def list_scan_runs(pool: asyncpg.Pool, where_clause: str, params: list[Any], limit: int, offset: int):
    return await pool.fetch(
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


async def get_scan_run(pool: asyncpg.Pool, scan_id: int):
    return await pool.fetchrow("SELECT * FROM scan_runs WHERE id = $1", scan_id)


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


async def fetch_latest_scans_by_host(pool: asyncpg.Pool):
    latest_scans_sql = """
        SELECT DISTINCT ON (hostname)
            hostname,
            success,
            reported_at,
            CAST(raw_scan_data->>'hardening_index' AS INTEGER) as score,
            CAST(raw_scan_data->>'warnings' AS INTEGER) as warnings
        FROM scan_runs
        ORDER BY hostname, reported_at DESC
    """

    async with pool.acquire() as conn:
        return await conn.fetch(latest_scans_sql)


async def count_failed_scans_24h(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM scan_runs WHERE success = false AND reported_at >= NOW() - INTERVAL '24 hours'"
        )
