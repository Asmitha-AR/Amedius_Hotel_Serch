"""Pulls TBO cities for every country in tbo_countries and upserts into tbo_cities.

Run from the hotel_website directory:
    python -m scripts.sync_tbo_cities                # all countries
    python -m scripts.sync_tbo_cities LK IN AE       # specific country codes
"""
import sys
import time

import requests
from psycopg2.extras import execute_values

from db.db import get_cursor, init_schema
from db.tbo_client import tbo_request


def _extract_city_rows(payload: dict, country_code: str) -> list[tuple[str, str, str]]:
    candidates = (
        payload.get("CityList")
        or payload.get("Cities")
        or payload.get("cityList")
        or []
    )
    rows: list[tuple[str, str, str]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        code = (entry.get("Code") or entry.get("CityCode") or entry.get("code") or "").strip()
        name = (entry.get("Name") or entry.get("CityName") or entry.get("name") or "").strip()
        if code and name:
            rows.append((code, name, country_code))
    return rows


def _all_country_codes() -> list[str]:
    with get_cursor() as cur:
        cur.execute("SELECT country_code FROM tbo_countries ORDER BY country_code")
        return [row[0] for row in cur.fetchall()]


def sync_cities(country_codes: list[str] | None = None, sleep_between: float = 0.2) -> int:
    init_schema()
    targets = country_codes or _all_country_codes()
    if not targets:
        print("No countries in tbo_countries. Run sync_tbo_countries first.")
        return 0

    sql = """
        INSERT INTO tbo_cities (tbo_city_code, city_name, country_code, fetched_at)
        VALUES %s
        ON CONFLICT (tbo_city_code) DO UPDATE
        SET city_name    = EXCLUDED.city_name,
            country_code = EXCLUDED.country_code,
            fetched_at   = NOW()
    """

    total = 0
    for idx, country_code in enumerate(targets, start=1):
        try:
            payload = tbo_request("POST", "CityList", {"CountryCode": country_code})
        except requests.RequestException as exc:
            print(f"[{idx}/{len(targets)}] {country_code}: request failed — {exc}")
            continue
        rows = _extract_city_rows(payload, country_code)
        if not rows:
            print(f"[{idx}/{len(targets)}] {country_code}: 0 cities")
            continue
        with get_cursor() as cur:
            execute_values(cur, sql, rows, template="(%s, %s, %s, NOW())")
        total += len(rows)
        print(f"[{idx}/{len(targets)}] {country_code}: upserted {len(rows)} cities")
        if sleep_between:
            time.sleep(sleep_between)

    print(f"Done. Total cities upserted: {total}")
    return total


if __name__ == "__main__":
    args = [a.strip().upper() for a in sys.argv[1:] if a.strip()]
    try:
        sync_cities(args or None)
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
