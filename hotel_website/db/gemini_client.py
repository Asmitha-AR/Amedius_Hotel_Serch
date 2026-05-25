"""Gemini client for batch resolving TBO city names → IATA city codes."""
import json
import os
import time

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "240"))
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "2"))


class GeminiError(RuntimeError):
    pass


def resolve_cities_to_iata(country_name: str, country_code: str, cities: list[dict]) -> dict[str, str | None]:
    """Given a list of {tbo_city_code, city_name}, return {tbo_city_code: iata_or_None}.

    Gemini is asked to return IATA city codes (3-letter) for cities that have one.
    Cities with no IATA code (small towns, etc.) get None.
    """
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY not set in .env")
    if not cities:
        return {}

    city_lines = "\n".join(f"- {c['tbo_city_code']}: {c['city_name']}" for c in cities)
    prompt = (
        f"You are a travel data assistant. Below is a list of cities in {country_name} "
        f"(ISO country code: {country_code}). Each line has a TBO city code and the city name.\n\n"
        f"For each city, return the official IATA city code (3-letter uppercase) if one exists. "
        f"If the city has no IATA city code (small town, no airport), return null.\n\n"
        f"Cities:\n{city_lines}\n\n"
        f"Return ONLY a JSON object mapping each TBO city code to its IATA code (or null). "
        f"Example: {{\"12345\": \"CMB\", \"67890\": null}}"
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    }

    url = GEMINI_ENDPOINT.format(model=GEMINI_MODEL)
    session = requests.Session()
    session.trust_env = False

    response = None
    last_exc: Exception | None = None
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        try:
            response = session.post(
                url,
                params={"key": GEMINI_API_KEY},
                json=body,
                timeout=GEMINI_TIMEOUT,
            )
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < GEMINI_MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
            else:
                raise GeminiError(f"Gemini request failed after {attempt + 1} attempts: {exc}")

    if response is None:
        raise GeminiError(f"Gemini request never completed: {last_exc}")
    if response.status_code >= 400:
        raise GeminiError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")

    payload = response.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiError(f"Gemini returned no candidates: {json.dumps(payload)[:500]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise GeminiError(f"Gemini returned empty text: {json.dumps(payload)[:500]}")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returned invalid JSON: {exc}; text={text[:300]}")

    if not isinstance(parsed, dict):
        raise GeminiError(f"Gemini returned non-object JSON: {text[:300]}")

    result: dict[str, str | None] = {}
    for c in cities:
        raw = parsed.get(c["tbo_city_code"])
        if isinstance(raw, str):
            code = raw.strip().upper()
            result[c["tbo_city_code"]] = code if len(code) == 3 and code.isalpha() else None
        else:
            result[c["tbo_city_code"]] = None
    return result
