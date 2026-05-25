"""Quick comparison: how many hotels does SOAP return vs REST for a given IATA city?

Run from hotel_website directory:
    python -m scripts.compare_soap_vs_rest DXB
"""
import sys

from db.amadeus_client import hotels_by_city as rest_hotels
from db.amadeus_soap import hotels_by_city_soap


def main(city_code: str) -> None:
    print(f"Comparing inventory for {city_code}...")

    print(f"  REST  → ", end="", flush=True)
    try:
        rest = rest_hotels(city_code)
        with_coords = sum(1 for h in rest if h.get("latitude") and h.get("longitude"))
        print(f"{len(rest)} hotels  ({with_coords} with coords)")
    except Exception as exc:
        print(f"FAILED: {exc}")
        rest = []

    print(f"  SOAP  → ", end="", flush=True)
    try:
        soap = hotels_by_city_soap(city_code)
        with_coords = sum(1 for h in soap if h.get("latitude") and h.get("longitude"))
        print(f"{len(soap)} hotels  ({with_coords} with coords)")
    except Exception as exc:
        print(f"FAILED: {exc}")
        soap = []

    if rest and soap:
        rest_ids = {h["hotelId"] for h in rest}
        soap_ids = {h["hotelId"] for h in soap}
        print(f"\n  Overlap: {len(rest_ids & soap_ids)}")
        print(f"  Only in REST: {len(rest_ids - soap_ids)}")
        print(f"  Only in SOAP: {len(soap_ids - rest_ids)}")

    if soap:
        print(f"\n  Sample SOAP hotels:")
        for h in soap[:10]:
            print(f"    {h['hotelId']:>10} {h['name'][:50]:<50} ({h['latitude']}, {h['longitude']})")


if __name__ == "__main__":
    city = (sys.argv[1] if len(sys.argv) > 1 else "DXB").upper()
    main(city)
