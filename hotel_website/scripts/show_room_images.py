"""Hit compare-prices and print per-offer image assignments + bucket sizes."""
import sys
import requests

city = "FJR"; tbo_id = "5015627"; amadeus_id = "HLFJR705"
url = (
    f"http://127.0.0.1:5050/api/mapping/compare-prices"
    f"?tbo_id={tbo_id}&amadeus_id={amadeus_id}&city={city}"
    f"&checkin=2026-07-26&checkout=2026-07-28&adults=2&rooms=1"
)
data = requests.get(url, timeout=120).json()
ama = data.get("amadeus") or {}
tbo = data.get("tbo") or {}
print(f"Amadeus: {ama.get('name')}  ({ama.get('hotelId')})")
for i, o in enumerate(ama.get("offers") or []):
    imgs = o.get("images") or []
    print(f"  #{i}  {(o.get('description') or '')[:50]:<50}  gallery={len(imgs)}")
print()
print(f"TBO: code {tbo.get('hotelCode')}  total rooms={tbo.get('roomCount')}")
for i, r in enumerate(tbo.get("rooms") or []):
    imgs = r.get("images") or []
    print(f"  #{i}  {(r.get('name') or '')[:50]:<50}  gallery={len(imgs)}")
