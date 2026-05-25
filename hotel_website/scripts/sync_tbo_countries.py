"""Pulls the full TBO country list and upserts it into tbo_countries.

Run from the hotel_website directory:
    python -m scripts.sync_tbo_countries
"""
import sys
from psycopg2.extras import execute_values

from db.db import get_cursor, init_schema
from db.tbo_client import tbo_request


def _extract_country_rows(payload: dict) -> list[tuple[str, str]]:
    candidates = (
        payload.get("CountryList")
        or payload.get("Countries")
        or payload.get("countryList")
        or []
    )
    rows: list[tuple[str, str]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        code = (entry.get("Code") or entry.get("CountryCode") or entry.get("code") or "").strip()
        name = (entry.get("Name") or entry.get("CountryName") or entry.get("name") or "").strip()
        if code and name:
            rows.append((code, name))
    return rows


def sync_countries() -> int:
    init_schema()
    payload = tbo_request("GET", "CountryList")
    rows = _extract_country_rows(payload)
    if not rows:
        print("TBO returned no countries. Raw keys:", list(payload.keys()))
        return 0
    sql = """
        INSERT INTO tbo_countries (country_code, country_name, fetched_at)
        VALUES %s
        ON CONFLICT (country_code) DO UPDATE
        SET country_name = EXCLUDED.country_name,
            fetched_at   = NOW()
    """
    with get_cursor() as cur:
        execute_values(cur, sql, rows, template="(%s, %s, NOW())")
    print(f"Upserted {len(rows)} countries.")
    return len(rows)


if __name__ == "__main__":
    try:
        sync_countries()
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
