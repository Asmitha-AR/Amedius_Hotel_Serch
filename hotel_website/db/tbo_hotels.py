"""TBO hotel fetchers: list hotels in a city, fetch details (with coords) by code."""
from db.tbo_client import tbo_request


def hotels_for_city(tbo_city_code: str) -> list[dict]:
    """Returns [{code, name, address, city, rating}] from TBOHotelCodeList."""
    code = str(tbo_city_code or "").strip()
    if not code:
        return []
    data = tbo_request("POST", "TBOHotelCodeList", {"CityCode": code})
    out = []
    for h in (data.get("Hotels") or []):
        out.append({
            "code": str(h.get("HotelCode") or ""),
            "name": h.get("HotelName") or "",
            "rating": h.get("HotelRating") or "",
            "address": h.get("Address") or "",
            "city": h.get("CityName") or "",
        })
    return [h for h in out if h["code"] and h["name"]]


def hotel_details(hotel_codes: list[str], language: str = "EN") -> dict[str, dict]:
    """Bulk-fetch hotel details for up to ~200 codes per call.

    Returns {hotel_code: {name, latitude, longitude, address}}.
    """
    codes = [str(c).strip() for c in hotel_codes if str(c).strip()]
    if not codes:
        return {}
    payload = {"Hotelcodes": ",".join(codes), "Language": language}
    data = tbo_request("POST", "HotelDetails", payload)

    result: dict[str, dict] = {}
    candidates = (
        data.get("HotelDetails")
        or data.get("Hotels")
        or data.get("hotelDetails")
        or []
    )
    for item in candidates:
        if not isinstance(item, dict):
            continue
        hotel_code = str(item.get("HotelCode") or item.get("hotelCode") or "").strip()
        if not hotel_code:
            continue
        lat = (
            item.get("Latitude")
            or item.get("Map", {}).get("Latitude") if isinstance(item.get("Map"), dict) else None
        )
        lon = (
            item.get("Longitude")
            or item.get("Map", {}).get("Longitude") if isinstance(item.get("Map"), dict) else None
        )
        if lat is None or lon is None:
            map_field = item.get("Map") or item.get("map") or ""
            if isinstance(map_field, str) and "|" in map_field:
                parts = map_field.split("|")
                if len(parts) == 2:
                    lat, lon = parts[0].strip(), parts[1].strip()
            elif isinstance(map_field, dict):
                lat = lat or map_field.get("Latitude") or map_field.get("latitude")
                lon = lon or map_field.get("Longitude") or map_field.get("longitude")

        result[hotel_code] = {
            "name": item.get("HotelName") or item.get("Name") or "",
            "latitude": lat,
            "longitude": lon,
            "address": item.get("Address") or "",
        }
    return result
