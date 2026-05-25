"""Resolve TBO cities → IATA city codes via Gemini, populate city_cd_mapping.

Run from the hotel_website directory:
    python -m scripts.resolve_iata_mapping              # all unresolved countries
    python -m scripts.resolve_iata_mapping LK IN AE     # specific country codes
    python -m scripts.resolve_iata_mapping --refresh LK # re-resolve even if mapped

Batching: cities are sent to Gemini in chunks of BATCH_SIZE per country to keep
prompts compact and avoid output truncation.
"""
import sys
import time

from psycopg2.extras import execute_values

from db.db import get_cursor, init_schema
from db.gemini_client import resolve_cities_to_iata, GeminiError

BATCH_SIZE = 30
SLEEP_BETWEEN_CALLS = 0.5


def _countries_to_process(country_codes: list[str] | None, refresh: bool) -> list[tuple[str, str]]:
    with get_cursor() as cur:
        if country_codes:
            cur.execute(
                "SELECT country_code, country_name FROM tbo_countries WHERE country_code = ANY(%s) ORDER BY country_code",
                (country_codes,),
            )
        else:
            cur.execute("SELECT country_code, country_name FROM tbo_countries ORDER BY country_code")
        return [(row[0], row[1]) for row in cur.fetchall()]


def _cities_to_resolve(country_code: str, refresh: bool) -> list[dict]:
    with get_cursor(dict_rows=True) as cur:
        if refresh:
            cur.execute(
                "SELECT tbo_city_code, city_name FROM tbo_cities WHERE country_code = %s ORDER BY tbo_city_code",
                (country_code,),
            )
        else:
            cur.execute(
                """
                SELECT c.tbo_city_code, c.city_name
                FROM tbo_cities c
                LEFT JOIN city_cd_mapping m ON m.tbo_city_code = c.tbo_city_code
                WHERE c.country_code = %s
                  AND m.tbo_city_code IS NULL
                ORDER BY c.tbo_city_code
                """,
                (country_code,),
            )
        return [dict(r) for r in cur.fetchall()]


def _persist(mapping_rows: list[tuple]) -> None:
    if not mapping_rows:
        return
    sql = """
        INSERT INTO city_cd_mapping
            (tbo_city_code, iata_city_code, city_name, country_code, resolver_source, resolved_at)
        VALUES %s
        ON CONFLICT (tbo_city_code) DO UPDATE
        SET iata_city_code  = EXCLUDED.iata_city_code,
            city_name       = EXCLUDED.city_name,
            country_code    = EXCLUDED.country_code,
            resolver_source = EXCLUDED.resolver_source,
            resolved_at     = NOW()
    """
    with get_cursor() as cur:
        execute_values(cur, sql, mapping_rows, template="(%s, %s, %s, %s, %s, NOW())")


def resolve(country_codes: list[str] | None = None, refresh: bool = False) -> dict[str, int]:
    init_schema()
    targets = _countries_to_process(country_codes, refresh)
    if not targets:
        print("No countries found.")
        return {"countries": 0, "resolved": 0, "mapped": 0}

    total_resolved = 0
    total_mapped = 0
    for idx, (country_code, country_name) in enumerate(targets, start=1):
        cities = _cities_to_resolve(country_code, refresh)
        if not cities:
            print(f"[{idx}/{len(targets)}] {country_code} {country_name}: no cities to resolve")
            continue

        country_mapped = 0
        for start in range(0, len(cities), BATCH_SIZE):
            batch = cities[start:start + BATCH_SIZE]
            try:
                result = resolve_cities_to_iata(country_name, country_code, batch)
            except GeminiError as exc:
                print(f"[{idx}/{len(targets)}] {country_code} batch {start}: Gemini failed — {exc}")
                continue

            rows = [
                (c["tbo_city_code"], result.get(c["tbo_city_code"]), c["city_name"], country_code, "gemini")
                for c in batch
            ]
            _persist(rows)
            mapped_in_batch = sum(1 for r in rows if r[1])
            country_mapped += mapped_in_batch
            total_resolved += len(rows)
            total_mapped += mapped_in_batch
            if SLEEP_BETWEEN_CALLS:
                time.sleep(SLEEP_BETWEEN_CALLS)

        print(f"[{idx}/{len(targets)}] {country_code} {country_name}: {len(cities)} cities, {country_mapped} with IATA")

    print(f"\nDone. Resolved {total_resolved} cities across {len(targets)} countries; {total_mapped} have IATA codes.")
    return {"countries": len(targets), "resolved": total_resolved, "mapped": total_mapped}


if __name__ == "__main__":
    args = sys.argv[1:]
    refresh = "--refresh" in args
    country_codes = [a.strip().upper() for a in args if a.strip() and not a.startswith("--")]
    try:
        resolve(country_codes or None, refresh=refresh)
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
