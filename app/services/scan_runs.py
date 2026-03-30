from typing import Any

import asyncpg
from fastapi import HTTPException

from app.db import scan_runs as scan_runs_db
from app.models import AttentionHost, DashboardStats, HardeningBuckets, ScanRunDetail, ScanRunsResponse, ScanRunSummary


def _build_where_clause(clauses: list[str]) -> str:
    return " AND ".join(clauses) if clauses else "TRUE"


async def fetch_scan_runs(
    pool: asyncpg.Pool, clauses: list[str], params: list[Any], limit: int, offset: int
) -> ScanRunsResponse:
    where_clause = _build_where_clause(clauses)
    total = await scan_runs_db.count_scan_runs(pool, where_clause, params)
    rows = await scan_runs_db.list_scan_runs(pool, where_clause, params, limit, offset)

    items = [ScanRunSummary.model_validate(dict(row)) for row in rows]
    return ScanRunsResponse(
        total=total,
        count=len(items),
        limit=limit,
        offset=offset,
        items=items,
    )


async def fetch_scan_detail(pool: asyncpg.Pool, scan_id: int) -> ScanRunDetail:
    row = await scan_runs_db.get_scan_run(pool, scan_id)

    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanRunDetail.model_validate(dict(row))


async def fetch_dashboard_stats(pool: asyncpg.Pool) -> DashboardStats:
    rows = await scan_runs_db.fetch_latest_scans_by_host(pool)

    total_hosts = len(rows)
    buckets = {"danger": 0, "medium": 0, "secure": 0}
    attention_list = []

    for row in rows:
        score = row["score"]
        warnings = row["warnings"] or 0

        if score is not None:
            if score < 50:
                buckets["danger"] += 1
            elif score <= 75:
                buckets["medium"] += 1
            else:
                buckets["secure"] += 1

        if not row["success"] or warnings > 0 or (score and score < 50):
            attention_list.append(
                AttentionHost(
                    hostname=row["hostname"],
                    last_score=score,
                    warning_count=warnings,
                    last_scan=row["reported_at"],
                )
            )

    failed_24h = await scan_runs_db.count_failed_scans_24h(pool)

    return DashboardStats(
        total_hosts=total_hosts,
        failed_scans_24h=failed_24h,
        buckets=HardeningBuckets(**buckets),
        needs_attention=attention_list[:10],
    )
