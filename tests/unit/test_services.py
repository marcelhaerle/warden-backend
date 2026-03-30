from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.services.scan_runs import fetch_scan_detail


class FakePool:
    async def fetchrow(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_fetch_scan_detail_raises_404_for_missing_scan(monkeypatch):
    async def _missing(_pool, _scan_id):
        return None

    monkeypatch.setattr("app.db.scan_runs.get_scan_run", _missing)

    with pytest.raises(HTTPException) as exc:
        await fetch_scan_detail(FakePool(), 999)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_scan_detail_returns_model(monkeypatch):
    async def _row(_pool, _scan_id):
        return {
            "id": 1,
            "agent_version": "1.0.0",
            "hostname": "host-a",
            "reported_at": datetime.now(timezone.utc),
            "success": True,
            "error": None,
            "result_count": 1,
            "raw_scan_data": {"hardening_index": "88"},
            "received_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr("app.db.scan_runs.get_scan_run", _row)

    detail = await fetch_scan_detail(FakePool(), 1)

    assert detail.id == 1
    assert detail.hostname == "host-a"
