from datetime import datetime
from typing import Any

from pydantic import BaseModel


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


class HardeningBuckets(BaseModel):
    danger: int
    medium: int
    secure: int


class AttentionHost(BaseModel):
    hostname: str
    last_score: int | None
    warning_count: int
    last_scan: datetime


class DashboardStats(BaseModel):
    total_hosts: int
    failed_scans_24h: int
    buckets: HardeningBuckets
    needs_attention: list[AttentionHost]
