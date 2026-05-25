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
print(f"Hotel: {ama.get('name')}  ({ama.get('hotelId')})")
print()
for i, o in enumerate(ama.get("offers") or []):
    imgs = o.get("images") or []
    print(f"  #{i}  {(o.get('description') or '')[:55]:<55}  gallery_size={len(imgs)}")
