import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException


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
