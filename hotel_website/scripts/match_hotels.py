"""Match TBO hotels ↔ Amadeus hotels for cities in city_cd_mapping.

Pipeline per city:
  1. Fetch Amadeus hotels (name + coords) via /reference-data/locations/hotels/by-city.
  2. Fetch TBO hotels (name + code) via TBOHotelCodeList.
  3. For each TBO hotel, shortlist Amadeus candidates with name_similarity >= PREFILTER.
  4. For shortlisted pairs, bulk-fetch TBO HotelDetails to get coords.
  5. Compute combined score (name + distance) and persist matches >= THRESHOLD.

Run from the hotel_website directory:
    python -m scripts.match_hotels LK              # all mapped cities in Sri Lanka
    python -m scripts.match_hotels --city CMB      # one IATA city
    python -m scripts.match_hotels                 # all countries with mapped cities
"""
import argparse
import sys
import time

from psycopg2.extras import execute_values

from db.amadeus_client import hotels_by_city, AmadeusError
from db.db import get_cursor, init_schema
from db.matching import combined_score, distance_score, haversine_meters, name_similarity
from db.tbo_hotels import hotels_for_city, hotel_details

NAME_PREFILTER = 0.55
SCORE_THRESHOLD = 0.80
DETAILS_BATCH = 100
SLEEP_BETWEEN_CITIES = 0.5


def _mapped_cities(country: str | None, iata: str | None) -> list[tuple[str, str, str, str]]:
    """Returns (tbo_city_code, iata_city_code, city_name, country_code) for mapped cities."""
    with get_cursor() as cur:
        if iata:
            cur.execute(
                """SELECT tbo_city_code, iata_city_code, city_name, country_code
                   FROM city_cd_mapping
                   WHERE iata_city_code = %s
                   ORDER BY tbo_city_code""",
                (iata.upper(),),
            )
        elif country:
            cur.execute(
                """SELECT tbo_city_code, iata_city_code, city_name, country_code
                   FROM city_cd_mapping
                   WHERE country_code = %s AND iata_city_code IS NOT NULL
                   ORDER BY tbo_city_code""",
                (country.upper(),),
            )
        else:
            cur.execute(
                """SELECT tbo_city_code, iata_city_code, city_name, country_code
                   FROM city_cd_mapping
                   WHERE iata_city_code IS NOT NULL
                   ORDER BY country_code, tbo_city_code"""
            )
        return [tuple(r) for r in cur.fetchall()]


def _shortlist(tbo_list: list[dict], ama_list: list[dict]) -> dict[str, list[tuple[float, dict]]]:
    """tbo_code → [(name_score, amadeus_hotel), ...] above NAME_PREFILTER, sorted desc."""
    shortlist: dict[str, list[tuple[float, dict]]] = {}
    for tbo in tbo_list:
        scored: list[tuple[float, dict]] = []
        for ama in ama_list:
            s = name_similarity(tbo["name"], ama["name"])
            if s >= NAME_PREFILTER:
                scored.append((s, ama))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            shortlist[tbo["code"]] = scored[:5]
    return shortlist


def _fetch_tbo_coords(tbo_codes: list[str]) -> dict[str, dict]:
    coords: dict[str, dict] = {}
    for i in range(0, len(tbo_codes), DETAILS_BATCH):
        chunk = tbo_codes[i:i + DETAILS_BATCH]
        try:
            coords.update(hotel_details(chunk))
        except Exception as exc:
            print(f"  HotelDetails batch {i}-{i+len(chunk)} failed: {exc}")
    return coords


def _persist(rows: list[tuple]) -> None:
    if not rows:
        return
    sql = """
        INSERT INTO hotel_id_mapping
            (tbo_hotel_code, amadeus_hotel_id, tbo_hotel_name, amadeus_hotel_name,
             iata_city_code, name_score, distance_meters, combined_score, matched_at)
        VALUES %s
        ON CONFLICT (tbo_hotel_code, amadeus_hotel_id) DO UPDATE
        SET tbo_hotel_name     = EXCLUDED.tbo_hotel_name,
            amadeus_hotel_name = EXCLUDED.amadeus_hotel_name,
            iata_city_code     = EXCLUDED.iata_city_code,
            name_score         = EXCLUDED.name_score,
            distance_meters    = EXCLUDED.distance_meters,
            combined_score     = EXCLUDED.combined_score,
            matched_at         = NOW()
    """
    with get_cursor() as cur:
        execute_values(cur, sql, rows, template="(%s, %s, %s, %s, %s, %s, %s, %s, NOW())")


def match_city(tbo_city_code: str, iata_city_code: str, city_name: str) -> tuple[int, int]:
    try:
        ama_list = hotels_by_city(iata_city_code)
    except AmadeusError as exc:
        print(f"  Amadeus failed for {iata_city_code}: {exc}")
        return (0, 0)
    if not ama_list:
        print(f"  No Amadeus hotels for {iata_city_code}")
        return (0, 0)

    try:
        tbo_list = hotels_for_city(tbo_city_code)
    except Exception as exc:
        print(f"  TBO list failed for {tbo_city_code}: {exc}")
        return (0, 0)
    if not tbo_list:
        print(f"  No TBO hotels for {tbo_city_code}")
        return (0, 0)

    print(f"  TBO={len(tbo_list)} Amadeus={len(ama_list)}")
    shortlist = _shortlist(tbo_list, ama_list)
    if not shortlist:
        print(f"  No name-prefilter candidates")
        return (0, 0)

    tbo_coords = _fetch_tbo_coords(list(shortlist.keys()))

    rows: list[tuple] = []
    for tbo_code, candidates in shortlist.items():
        tbo_meta = next((h for h in tbo_list if h["code"] == tbo_code), None)
        if tbo_meta is None:
            continue
        tbo_lat = tbo_coords.get(tbo_code, {}).get("latitude")
        tbo_lon = tbo_coords.get(tbo_code, {}).get("longitude")

        best = None
        for name_score, ama in candidates:
            dist = haversine_meters(tbo_lat, tbo_lon, ama.get("latitude"), ama.get("longitude"))
            d_score = distance_score(dist)
            score = combined_score(name_score, d_score)
            if best is None or score > best[0]:
                best = (score, name_score, dist, ama)

        if best and best[0] >= SCORE_THRESHOLD:
            score, name_score, dist, ama = best
            rows.append((
                tbo_code,
                ama["hotelId"],
                tbo_meta["name"],
                ama["name"],
                iata_city_code,
                round(name_score, 4),
                round(dist, 2) if dist is not None else None,
                round(score, 4),
            ))

    _persist(rows)
    return (len(shortlist), len(rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("country", nargs="?", default=None, help="ISO country code (e.g. LK)")
    parser.add_argument("--city", default=None, help="IATA city code (e.g. CMB) — overrides country")
    args = parser.parse_args()

    init_schema()
    cities = _mapped_cities(args.country, args.city)
    if not cities:
        print("No mapped cities to process.")
        return

    total_pairs = 0
    total_matches = 0
    for idx, (tbo_city, iata_city, city_name, country_code) in enumerate(cities, start=1):
        print(f"[{idx}/{len(cities)}] {country_code}/{city_name} (tbo={tbo_city}, iata={iata_city})")
        pairs, matches = match_city(tbo_city, iata_city, city_name)
        total_pairs += pairs
        total_matches += matches
        if SLEEP_BETWEEN_CITIES:
            time.sleep(SLEEP_BETWEEN_CITIES)

    print(f"\nDone. {total_pairs} candidate pairs, {total_matches} matches persisted (threshold {SCORE_THRESHOLD}).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
