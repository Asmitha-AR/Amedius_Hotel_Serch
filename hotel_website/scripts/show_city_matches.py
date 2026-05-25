"""Show all matches for a given IATA city."""
import sys
from contextlib import ExitStack
from db.db import get_cursor

city = (sys.argv[1] if len(sys.argv) > 1 else "FJR").upper()

with ExitStack() as s:
    cur = s.enter_context(get_cursor())
    cur.execute(
        "SELECT tbo_hotel_name, amadeus_hotel_name, name_score, distance_meters, combined_score "
        "FROM hotel_id_mapping WHERE iata_city_code=%s ORDER BY combined_score DESC",
        (city,),
    )
    rows = cur.fetchall()
    print(f"{len(rows)} matches for {city}:")
    print()
    for r in rows:
        dist = f"{r[3]}m" if r[3] is not None else "n/a"
        print(f"  {r[4]:.3f} (name={r[2]:.2f}, dist={dist})")
        print(f"    TBO: {r[0]}")
        print(f"    AMA: {r[1]}")
        print()
