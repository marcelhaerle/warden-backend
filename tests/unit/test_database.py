from datetime import timezone

from app.core.database import parse_reported_at


def test_parse_reported_at_parses_z_suffix_as_utc():
    parsed = parse_reported_at("2026-03-30T10:20:30Z")

    assert parsed.year == 2026
    assert parsed.tzinfo == timezone.utc
