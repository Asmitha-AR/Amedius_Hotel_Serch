"""Read-only DB queries used by the Flask comparison endpoints."""
from db.db import get_cursor


def list_mapped_cities() -> list[dict]:
    """Returns cities that have at least one hotel match, with match count."""
    sql = """
        SELECT m.iata_city_code,
               MIN(c.city_name)    AS city_name,
               MIN(c.country_code) AS country_code,
               COUNT(*)            AS match_count
        FROM hotel_id_mapping m
        LEFT JOIN city_cd_mapping c ON c.iata_city_code = m.iata_city_code
        GROUP BY m.iata_city_code
        ORDER BY match_count DESC, m.iata_city_code
    """
    with get_cursor(dict_rows=True) as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def list_mapped_hotels(iata_city_code: str) -> list[dict]:
    """All matched hotel pairs for the given IATA city, sorted by combined_score."""
    sql = """
        SELECT tbo_hotel_code, amadeus_hotel_id, tbo_hotel_name, amadeus_hotel_name,
               iata_city_code, name_score, distance_meters, combined_score, matched_at
        FROM hotel_id_mapping
        WHERE iata_city_code = %s
        ORDER BY combined_score DESC, tbo_hotel_name
    """
    with get_cursor(dict_rows=True) as cur:
        cur.execute(sql, (iata_city_code.upper(),))
        out = []
        for r in cur.fetchall():
            row = dict(r)
            # Convert Decimal to float for JSON serialisation.
            for key in ("name_score", "distance_meters", "combined_score"):
                if row.get(key) is not None:
                    row[key] = float(row[key])
            if row.get("matched_at"):
                row["matched_at"] = row["matched_at"].isoformat()
            out.append(row)
        return out
