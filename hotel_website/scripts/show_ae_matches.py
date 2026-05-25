from contextlib import ExitStack
from db.db import get_cursor

with ExitStack() as s:
    cur = s.enter_context(get_cursor())
    cur.execute(
        "SELECT iata_city_code, COUNT(*) FROM hotel_id_mapping "
        "WHERE iata_city_code IN ('AAN','AUH','DXB','FJR','RKT','SHJ') "
        "GROUP BY iata_city_code ORDER BY iata_city_code"
    )
    print("Matches per AE city:")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")
    print()

    cur.execute(
        "SELECT tbo_hotel_name, amadeus_hotel_name, name_score, distance_meters, combined_score "
        "FROM hotel_id_mapping WHERE iata_city_code='DXB' "
        "ORDER BY combined_score DESC LIMIT 15"
    )
    print("Top 15 DXB matches:")
    for r in cur.fetchall():
        dist = f"{r[3]}m" if r[3] is not None else "n/a"
        print(f"  {r[4]:.3f} (name={r[2]:.2f}, dist={dist})  TBO: {r[0]}  AMA: {r[1]}")

    cur.execute(
        "SELECT iata_city_code, tbo_hotel_name, amadeus_hotel_name, combined_score "
        "FROM hotel_id_mapping WHERE iata_city_code IN ('AAN','AUH','FJR','RKT','SHJ') "
        "ORDER BY iata_city_code, combined_score DESC"
    )
    print()
    print("Other AE city matches:")
    for r in cur.fetchall():
        print(f"  [{r[0]}] {r[3]:.3f}  {r[1]}  =  {r[2]}")
