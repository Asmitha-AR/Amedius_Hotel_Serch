"""Amadeus REST client: OAuth token + hotels-by-city (with geo coords)."""
import os
import time

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

AMADEUS_REST_BASE = os.environ.get("AMADEUS_REST_BASE", "https://test.api.amadeus.com")
AMADEUS_API_KEY = os.environ.get("AMADEUS_API_KEY")
AMADEUS_API_SECRET = os.environ.get("AMADEUS_API_SECRET")

_token_cache = {"value": None, "expires_at": 0.0}


class AmadeusError(RuntimeError):
    pass


def _token() -> str:
    now = time.time()
    if _token_cache["value"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["value"]
    if not AMADEUS_API_KEY or not AMADEUS_API_SECRET:
        raise AmadeusError("AMADEUS_API_KEY / AMADEUS_API_SECRET not set in .env")
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        f"{AMADEUS_REST_BASE.rstrip('/')}/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": AMADEUS_API_KEY,
            "client_secret": AMADEUS_API_SECRET,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise AmadeusError(f"Token HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    _token_cache["value"] = data.get("access_token")
    _token_cache["expires_at"] = now + int(data.get("expires_in", 1799))
    return _token_cache["value"]


def hotels_by_city(iata_city_code: str) -> list[dict]:
    """Returns [{hotelId, name, latitude, longitude, chainCode}] for the city."""
    code = (iata_city_code or "").upper().strip()
    if not code:
        return []
    token = _token()
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        f"{AMADEUS_REST_BASE.rstrip('/')}/v1/reference-data/locations/hotels/by-city",
        params={"cityCode": code},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code == 404:
        return []
    if response.status_code >= 400:
        raise AmadeusError(f"hotels-by-city HTTP {response.status_code}: {response.text[:300]}")
    items = response.json().get("data") or []
    out = []
    for item in items:
        geo = item.get("geoCode") or {}
        out.append({
            "hotelId": item.get("hotelId") or "",
            "name": item.get("name") or "",
            "latitude": geo.get("latitude"),
            "longitude": geo.get("longitude"),
            "chainCode": item.get("chainCode") or "",
        })
    return out
