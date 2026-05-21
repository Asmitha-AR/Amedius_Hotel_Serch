from flask import Flask, render_template, request, jsonify
import os
import requests

app = Flask(__name__)

API_KEY    = os.environ.get("AMADEUS_API_KEY")
API_SECRET = os.environ.get("AMADEUS_API_SECRET")
BASE       = "https://test.api.amadeus.com"

_token_cache = {"token": None}

def get_token():
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Set AMADEUS_API_KEY and AMADEUS_API_SECRET before calling the Amadeus API.")

    r = requests.post(f"{BASE}/v1/security/oauth2/token", data={
        "grant_type":    "client_credentials",
        "client_id":     API_KEY,
        "client_secret": API_SECRET,
    }, timeout=10)
    r.raise_for_status()
    _token_cache["token"] = r.json()["access_token"]
    return _token_cache["token"]

def headers():
    return {"Authorization": f"Bearer {get_token()}"}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/search-hotels")
def search_hotels():
    city      = request.args.get("city", "DXB").upper()
    checkin   = request.args.get("checkin")
    checkout  = request.args.get("checkout")
    adults    = request.args.get("adults", 2)

    # Step 1: get hotel list for the city
    r1 = requests.get(f"{BASE}/v1/reference-data/locations/hotels/by-city",
        headers=headers(),
        params={"cityCode": city, "radius": 10, "radiusUnit": "KM", "hotelSource": "ALL"},
        timeout=15)
    if r1.status_code != 200:
        return jsonify({"error": r1.json()}), r1.status_code

    hotels = r1.json().get("data", [])[:20]
    if not hotels:
        return jsonify({"hotels": [], "message": "No hotels found for this city."})

    hotel_ids = [h["hotelId"] for h in hotels]

    # Step 2: get availability + pricing
    r2 = requests.get(f"{BASE}/v3/shopping/hotel-offers",
        headers=headers(),
        params={
            "hotelIds":    ",".join(hotel_ids),
            "checkInDate":  checkin,
            "checkOutDate": checkout,
            "adults":       adults,
            "currency":     "USD",
            "bestRateOnly": "true",
        },
        timeout=20)

    available = {}
    if r2.status_code == 200:
        for item in r2.json().get("data", []):
            hid = item["hotel"]["hotelId"]
            available[hid] = item

    # Build response
    result = []
    for h in hotels:
        hid  = h["hotelId"]
        item = available.get(hid)

        rec = {
            "hotelId":   hid,
            "name":      h.get("name", ""),
            "chainCode": h.get("chainCode", ""),
            "city":      h.get("iataCode", city),
            "latitude":  h.get("geoCode", {}).get("latitude"),
            "longitude": h.get("geoCode", {}).get("longitude"),
            "address":   " ".join(h.get("address", {}).get("lines", [])),
            "country":   h.get("address", {}).get("countryCode", ""),
            "available": item is not None,
            "offers":    [],
        }

        if item:
            for o in item.get("offers", [])[:5]:
                room     = o.get("room", {})
                price    = o.get("price", {})
                policies = o.get("policies", {})
                te       = room.get("typeEstimated", {})
                cancel   = policies.get("cancellations", [])
                refund   = policies.get("refundable", {}).get("cancellationRefund", "")
                avg      = price.get("variations", {}).get("average", {})

                rec["offers"].append({
                    "offerId":      o.get("id"),
                    "roomType":     room.get("type", ""),
                    "description":  room.get("description", {}).get("text", "")[:120],
                    "beds":         te.get("beds", ""),
                    "bedType":      te.get("bedType", ""),
                    "boardType":    o.get("boardType", "ROOM_ONLY"),
                    "basePrice":    price.get("base", ""),
                    "totalPrice":   price.get("total", ""),
                    "avgPerNight":  avg.get("base", avg.get("total", "")),
                    "currency":     price.get("currency", "USD"),
                    "paymentType":  policies.get("paymentType", ""),
                    "refundable":   refund,
                    "cancelDeadline": cancel[0].get("deadline", "") if cancel else "",
                    "cancelAmount":   cancel[0].get("amount", "") if cancel else "",
                })

        result.append(rec)

    available_only = [h for h in result if h["available"]]
    not_available  = [h for h in result if not h["available"]]
    return jsonify({"hotels": available_only + not_available})

@app.route("/api/offer-detail/<offer_id>")
def offer_detail(offer_id):
    r = requests.get(f"{BASE}/v3/shopping/hotel-offers/{offer_id}",
        headers=headers(), timeout=15)
    if r.status_code != 200:
        return jsonify({"error": r.json()}), r.status_code
    data = r.json().get("data", {})
    offers = data.get("offers", [{}])
    offer  = offers[0] if offers else {}
    price  = offer.get("price", {})
    return jsonify({
        "taxes":       price.get("taxes", []),
        "description": offer.get("description", {}).get("text", ""),
        "amenities":   data.get("hotel", {}).get("amenities", []),
        "address":     data.get("hotel", {}).get("address", {}),
    })

if __name__ == "__main__":
    app.run(debug=True, port=5050)
