"""Dump raw SOAP availability response to inspect element structure."""
import sys
from datetime import datetime, timedelta

import requests

from db.amadeus_soap import (
    _build_envelope, _build_inventory_body, AVAILABILITY_ACTION, SOAP_ENDPOINT,
)


def main(city: str) -> None:
    checkin = (datetime.utcnow() + timedelta(days=75)).strftime("%Y-%m-%d")
    checkout = (datetime.utcnow() + timedelta(days=76)).strftime("%Y-%m-%d")
    body = _build_inventory_body(city, checkin, checkout)
    envelope = _build_envelope(AVAILABILITY_ACTION, body)
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        SOAP_ENDPOINT,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": AVAILABILITY_ACTION},
        timeout=90,
    )
    path = f"soap_dump_{city}.xml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(response.text)
    print(f"status {response.status_code}, {len(response.text)} bytes -> {path}")

    text = response.text.lower()
    print()
    print("element presence in response:")
    for needle in ("position", "latitude", "longitude", "basicpropertyinfo", "hotelinfo", "hotelstay"):
        print(f"  {needle:<20} count={text.count(needle)}")


if __name__ == "__main__":
    main((sys.argv[1] if len(sys.argv) > 1 else "DXB").upper())
