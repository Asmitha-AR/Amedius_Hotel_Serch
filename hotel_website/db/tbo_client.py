import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TBO_BASE_URL = os.environ.get("TBO_BASE_URL", "https://apiwr.tboholidays.com/HotelAPI")
TBO_USERNAME = os.environ.get("TBO_USERNAME")
TBO_PASSWORD = os.environ.get("TBO_PASSWORD")


def tbo_request(method: str, endpoint: str, payload: dict | None = None) -> dict:
    if not TBO_USERNAME or not TBO_PASSWORD:
        raise RuntimeError("Set TBO_USERNAME and TBO_PASSWORD in .env before calling TBO APIs.")
    url = f"{TBO_BASE_URL.rstrip('/')}/{endpoint}"
    session = requests.Session()
    session.trust_env = False
    auth = (TBO_USERNAME, TBO_PASSWORD)
    if method.upper() == "GET":
        response = session.get(url, auth=auth, timeout=60)
    else:
        response = session.post(url, json=payload or {}, auth=auth, timeout=60)
    response.raise_for_status()
    return response.json()
