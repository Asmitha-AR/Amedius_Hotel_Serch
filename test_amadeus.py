"""
Amadeus Hotel API — Final Test Script
Self-Service REST API (free sandbox + production)
Office ID: DXBAD32AQ
"""

import requests
import json
import os
from datetime import datetime, timedelta

API_KEY    = os.environ.get("AMADEUS_API_KEY")
API_SECRET = os.environ.get("AMADEUS_API_SECRET")
BASE       = "https://test.api.amadeus.com"  # Change to https://api.amadeus.com for production

def get_token():
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Set AMADEUS_API_KEY and AMADEUS_API_SECRET before running this test.")

    r = requests.post(f"{BASE}/v1/security/oauth2/token", data={
        "grant_type": "client_credentials",
        "client_id": API_KEY,
        "client_secret": API_SECRET
    })
    if r.status_code == 200:
        return r.json()["access_token"]
    raise Exception(f"Auth failed: {r.text}")

def search_hotels_by_city(token, city_code="DXB", radius=5):
    """Search hotels by IATA city code"""
    r = requests.get(f"{BASE}/v1/reference-data/locations/hotels/by-city",
        headers={"Authorization": f"Bearer {token}"},
        params={"cityCode": city_code, "radius": radius, "radiusUnit": "KM", "hotelSource": "ALL"})
    return r.status_code, r.json()

def search_hotels_by_ids(token, hotel_ids: list):
    """Look up specific hotels by their IDs"""
    r = requests.get(f"{BASE}/v1/reference-data/locations/hotels/by-hotels",
        headers={"Authorization": f"Bearer {token}"},
        params={"hotelIds": ",".join(hotel_ids)})
    return r.status_code, r.json()

def search_hotels_by_keyword(token, keyword, country_code="AE"):
    """Search hotels by name keyword"""
    r = requests.get(f"{BASE}/v1/reference-data/locations/hotels/by-keyword",
        headers={"Authorization": f"Bearer {token}"},
        params={"keyword": keyword, "countryCode": country_code})
    return r.status_code, r.json()

def get_hotel_offers(token, hotel_ids: list, checkin, checkout, adults=2,
                     rooms=1, currency="USD", best_rate_only=False):
    """Get room availability and pricing for hotels"""
    r = requests.get(f"{BASE}/v3/shopping/hotel-offers",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "hotelIds":    ",".join(hotel_ids),
            "checkInDate":  checkin,
            "checkOutDate": checkout,
            "adults":       adults,
            "roomQuantity": rooms,
            "currency":     currency,
            "bestRateOnly": str(best_rate_only).lower()
        })
    return r.status_code, r.json()

def get_offer_detail(token, offer_id):
    """Get full details for a specific offer (includes full taxes breakdown)"""
    r = requests.get(f"{BASE}/v3/shopping/hotel-offers/{offer_id}",
        headers={"Authorization": f"Bearer {token}"})
    return r.status_code, r.json()

def print_hotel_summary(hotel_data):
    """Pretty print hotel data"""
    h = hotel_data.get("hotel", hotel_data)
    print(f"  Hotel ID:   {h.get('hotelId','')}")
    print(f"  Name:       {h.get('name','')}")
    print(f"  City:       {h.get('cityCode', h.get('iataCode',''))}")
    print(f"  Lat/Lng:    {h.get('latitude', h.get('geoCode',{}).get('latitude',''))}, "
          f"{h.get('longitude', h.get('geoCode',{}).get('longitude',''))}")
    addr = h.get("address", {})
    print(f"  Address:    {', '.join(addr.get('lines',[]))} {addr.get('cityName','')} {addr.get('countryCode','')}")
    print(f"  Chain:      {h.get('chainCode','')}")

def print_offer_summary(offer):
    """Pretty print an offer"""
    room = offer.get("room", {})
    price = offer.get("price", {})
    policies = offer.get("policies", {})
    cancellations = policies.get("cancellations", [])

    print(f"  Offer ID:      {offer.get('id','')}")
    print(f"  Check-in:      {offer.get('checkInDate','')}")
    print(f"  Check-out:     {offer.get('checkOutDate','')}")
    print(f"  Room type:     {room.get('type','')}")
    te = room.get("typeEstimated", {})
    print(f"  Bed type:      {te.get('beds','?')} x {te.get('bedType','')}")
    print(f"  Description:   {room.get('description',{}).get('text','')[:80]}")
    print(f"  Board type:    {offer.get('boardType','N/A')}")
    print(f"  Base price:    {price.get('base','N/A')} {price.get('currency','')}")
    print(f"  Total price:   {price.get('total','N/A')} {price.get('currency','')}")
    avg = price.get("variations", {}).get("average", {})
    print(f"  Avg/night:     {avg.get('base', avg.get('total','N/A'))} {price.get('currency','')}")
    print(f"  Payment type:  {policies.get('paymentType','')}")
    refund = policies.get("refundable", {})
    print(f"  Refundable:    {refund.get('cancellationRefund','')}")
    for c in cancellations[:2]:
        deadline = c.get("deadline", "No deadline")
        amount   = c.get("amount", "N/A")
        nights   = c.get("numberOfNights", "")
        nights_str = f" ({nights} nights)" if nights else ""
        print(f"  Cancel policy: Deadline={deadline}, Penalty={amount}{nights_str}")

def run_all_tests():
    checkin  = (datetime.today() + timedelta(days=35)).strftime("%Y-%m-%d")
    checkout = (datetime.today() + timedelta(days=37)).strftime("%Y-%m-%d")

    print("=" * 60)
    print("AMADEUS HOTEL API TEST")
    print(f"Dates: {checkin} → {checkout}")
    print("=" * 60)

    token = get_token()
    print(f"[AUTH] Token OK\n")

    # ─── TEST 1: Search by city ─────────────────────────────
    print("TEST 1: Search by city code (DXB)")
    status, data = search_hotels_by_city(token, "DXB")
    hotels = data.get("data", [])
    print(f"  HTTP {status} | Hotels found: {len(hotels)}")
    if hotels:
        print_hotel_summary(hotels[0])

    print()

    # ─── TEST 2: Hotel offers ────────────────────────────────
    print("TEST 2: Hotel offers (room availability + price)")
    # Use known working hotels
    status, data = get_hotel_offers(token, ["ALNYC647"], checkin, checkout, adults=2)
    print(f"  HTTP {status}")
    offers_list = data.get("data", [])
    if offers_list:
        hotel_obj = offers_list[0]
        print_hotel_summary(hotel_obj)
        offers = hotel_obj.get("offers", [])
        print(f"  Offers returned: {len(offers)}")
        print()
        for o in offers[:3]:
            print_offer_summary(o)
            print()

    # ─── TEST 3: Single offer detail (full taxes) ────────────
    if offers_list and offers_list[0].get("offers"):
        offer_id = offers_list[0]["offers"][0]["id"]
        print(f"TEST 3: Single offer detail (offer {offer_id})")
        status3, detail = get_offer_detail(token, offer_id)
        print(f"  HTTP {status3}")
        if status3 == 200:
            taxes = detail.get("data",{}).get("offers",[{}])[0].get("price",{}).get("taxes",[])
            print(f"  Tax lines: {len(taxes)}")
            for t in taxes:
                inc = "included" if t.get("included") else "extra"
                print(f"    {t.get('code','?')}: {t.get('amount')} {t.get('currency')} ({inc})")

    print()

    # ─── TEST 4: Meal plan ───────────────────────────────────
    print("TEST 4: Hotel with meal plan (HALF_BOARD test)")
    status4, data4 = get_hotel_offers(token, ["UHNYC000"],
        checkin, (datetime.today() + timedelta(days=36)).strftime("%Y-%m-%d"), adults=2)
    print(f"  HTTP {status4}")
    for item in data4.get("data",[])[:1]:
        for o in item.get("offers",[])[:2]:
            board = o.get("boardType","N/A")
            total = o.get("price",{}).get("total","")
            print(f"  Board: {board} | Total: {total} USD")

    print()
    print("=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    run_all_tests()
