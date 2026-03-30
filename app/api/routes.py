from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_db_pool
from app.models import DashboardStats, ScanRunDetail, ScanRunsResponse
from app.services.filters import build_metadata_filters, parse_json_contains
from app.services.scan_runs import fetch_dashboard_stats, fetch_scan_detail, fetch_scan_runs

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "Warden backend is running", "worker": "active"}


@router.get("/api/scans", response_model=ScanRunsResponse)
async def list_scan_results(
    hostname: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    agent_version: str | None = Query(default=None),
    reported_from: datetime | None = Query(default=None),
    reported_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    clauses, params = build_metadata_filters(
        hostname=hostname,
        success=success,
        agent_version=agent_version,
        reported_from=reported_from,
        reported_to=reported_to,
    )

    return await fetch_scan_runs(
        pool=pool,
        clauses=clauses,
        params=params,
        limit=limit,
        offset=offset,
    )


@router.get("/api/scans/search", response_model=ScanRunsResponse)
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
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    if (json_key is None) != (json_value is None):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="json_key and json_value must be provided together",
        )

    if json_key is None and json_contains is None:
        from fastapi import HTTPException

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
        pool=pool,
        clauses=clauses,
        params=params,
        limit=limit,
        offset=offset,
    )


@router.get("/api/scans/{scan_id}", response_model=ScanRunDetail)
async def get_scan_detail(scan_id: int, pool: asyncpg.Pool = Depends(get_db_pool)):
    return await fetch_scan_detail(pool, scan_id)


@router.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard(pool: asyncpg.Pool = Depends(get_db_pool)):
    return await fetch_dashboard_stats(pool)
