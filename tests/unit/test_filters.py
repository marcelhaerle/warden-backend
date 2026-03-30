import pytest
from fastapi import HTTPException

from app.services.filters import build_metadata_filters, parse_json_contains


def test_build_metadata_filters_populates_all_supported_fields():
    clauses, params = build_metadata_filters(
        hostname="web",
        success=True,
        agent_version="1.0.0",
        reported_from=None,
        reported_to=None,
    )

    assert clauses == [
        "hostname ILIKE $1",
        "success = $2",
        "agent_version = $3",
    ]
    assert params == ["%web%", True, "1.0.0"]


def test_parse_json_contains_accepts_json_object():
    result = parse_json_contains('{"warnings":"0"}')
    assert result == '{"warnings": "0"}'


@pytest.mark.parametrize("value", ["{", "[]"])
def test_parse_json_contains_rejects_invalid_or_non_object(value: str):
    with pytest.raises(HTTPException):
        parse_json_contains(value)
