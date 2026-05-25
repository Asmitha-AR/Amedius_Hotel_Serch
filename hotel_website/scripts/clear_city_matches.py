"""Delete hotel_id_mapping rows for given IATA city codes.

Usage:
    python -m scripts.clear_city_matches AAN AUH DXB FJR RKT SHJ
"""
import sys
from contextlib import ExitStack
from db.db import get_cursor

codes = [c.strip().upper() for c in sys.argv[1:] if c.strip()]
if not codes:
    print("Pass IATA codes to clear, e.g. AAN AUH DXB")
    sys.exit(1)

with ExitStack() as s:
    cur = s.enter_context(get_cursor())
    cur.execute(
        "DELETE FROM hotel_id_mapping WHERE iata_city_code = ANY(%s)",
        (codes,),
    )
    print(f"Deleted {cur.rowcount} matches for {codes}")
