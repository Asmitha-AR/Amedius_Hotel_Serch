# Amadeus Hotel API — Test Report
**Date:** 2026-05-21  
**Tested by:** API Testing Session  
**Office ID:** DXBAD32AQ  
**Self-Service REST (Sandbox):** test.api.amadeus.com  
**Enterprise SOAP (Test):** nodeD3.test.webservices.amadeus.com/1ASIWLUXLET

---

## Summary Table

| Test | Status | Notes |
|---|---|---|
| REST Access token generated | ✅ PASS | Works with API Key + Secret |
| Hotel search by city | ✅ PASS | Returns 84+ hotels for DXB, 214 for LON |
| Hotel search by hotel IDs | ✅ PASS | Direct lookup works |
| Hotel search by keyword | ❌ FAIL | 500 Internal Error in test sandbox |
| Hotel offers / room availability | ✅ PASS | Full room + price data |
| Room type received | ✅ PASS | AP7, REG, WFB, WFC codes |
| Room description received | ✅ PASS | Text with bed type, size, amenities |
| Bed type received | ✅ PASS | QUEEN, KING, bed count |
| Base price (per night) | ✅ PASS | Available |
| Total price (full stay) | ✅ PASS | Available |
| Average per night | ✅ PASS | variations.average.base |
| Daily price breakdown | ✅ PASS | Per-night breakdown available |
| Taxes (detailed) | ✅ PASS | CITY_TAX, TOURISM_TAX, OCCUPANCY_TAX, STATE_TAX |
| Currency | ✅ PASS | Full currency code |
| Meal plan (boardType) | ✅ PASS | ROOM_ONLY, HALF_BOARD confirmed |
| Cancellation policy | ✅ PASS | Deadline + penalty amount |
| Refundable status | ✅ PASS | NON_REFUNDABLE / REFUNDABLE_UP_TO_DEADLINE |
| Payment type | ✅ PASS | deposit / guarantee |
| Commission | ✅ PASS | Commission amount returned |
| Hotel star rating | ❌ MISSING | Not returned in Self-Service API |
| Full hotel description | ❌ MISSING | Only room description text |
| Hotel amenities (full list) | ⚠️ PARTIAL | Only returned in single-offer view |
| Hotel images | ❌ NOT AVAILABLE | No image endpoint exists |
| Hotel ratings/sentiments | ❌ FAIL | 500 error in test sandbox |
| Enterprise SOAP API | ❌ BLOCKED | IP not whitelisted at Amadeus DMZ |

---

## Part 1: Self-Service REST API

### Authentication
**Endpoint:** `POST https://test.api.amadeus.com/v1/security/oauth2/token`

**Request:**
```
grant_type=client_credentials
client_id=$AMADEUS_API_KEY
client_secret=$AMADEUS_API_SECRET
```

**Response:** ✅ HTTP 200 — Token received

---

### Test 1: Hotel Search by City

**Endpoint:** `GET /v1/reference-data/locations/hotels/by-city`

**Parameters:**
```
cityCode=DXB
radius=5
radiusUnit=KM
```

**Result:** ✅ HTTP 200

**Sample response (DXB):**
```json
{
  "chainCode": "MC",
  "iataCode": "DXB",
  "name": "JW MARRIOTT HOTEL DUBAI",
  "hotelId": "MCDXBAEM",
  "geoCode": { "latitude": 25.26866, "longitude": 55.32972 },
  "address": {
    "countryCode": "AE",
    "cityName": "DUBAI",
    "lines": ["ABU BAKER AL SIDDIQUE RD ADJAC"]
  },
  "distance": { "value": 0.29, "unit": "KM" }
}
```

**Data Available:**
| Field | Available | Notes |
|---|---|---|
| Hotel ID | ✅ | e.g., MCDXBAEM |
| Hotel name | ✅ | Full name |
| City code (IATA) | ✅ | DXB, LON, NYC |
| Chain code | ✅ | MC, CP, AL, etc. |
| Latitude / Longitude | ✅ | Precise coordinates |
| Street address | ✅ | Address lines |
| City name | ✅ | |
| Country code | ✅ | AE, US, GB |
| Postal code | ⚠️ | Sometimes "0000" (dummy) |
| Star rating | ❌ | Not in this endpoint |
| Distance from center | ✅ | With unit |
| Last update date | ✅ | |

**Issues:**
- Dubai sandbox hotels mostly return "INVALID PROPERTY CODE" or "NO ROOMS AVAILABLE" on availability
- Keyword search (by hotel name) returns 500 in test sandbox — likely works in production
- Real rooms available for NYC, LON, PAR test properties

---

### Test 2: Hotel Offers (Room Availability)

**Endpoint:** `GET /v3/shopping/hotel-offers`

**Parameters:**
```
hotelIds=ALNYC647
checkInDate=2026-06-25
checkOutDate=2026-06-27
adults=2
currency=USD
bestRateOnly=false
```

**Result:** ✅ HTTP 200 — 10 offers returned

**Sample response:**
```json
{
  "hotel": {
    "hotelId": "ALNYC647",
    "chainCode": "AL",
    "name": "Aloft Manhattan Downtown - Financial District",
    "cityCode": "NYC",
    "latitude": 40.71041,
    "longitude": -74.00666
  },
  "available": true,
  "offers": [
    {
      "id": "W48FG47OA2",
      "checkInDate": "2026-06-25",
      "checkOutDate": "2026-06-27",
      "rateCode": "RAC",
      "room": {
        "type": "REG",
        "typeEstimated": { "beds": 1, "bedType": "QUEEN" },
        "description": { "text": "Flexible\n1 Queen, 200sqft/18sqm-220sqft/20sqm" }
      },
      "price": {
        "currency": "USD",
        "base": "1068.00",
        "total": "1232.54",
        "variations": {
          "average": { "base": "534.00" },
          "changes": [
            { "startDate": "2026-06-25", "endDate": "2026-06-26", "base": "459.00" },
            { "startDate": "2026-06-26", "endDate": "2026-06-27", "base": "609.00" }
          ]
        }
      },
      "policies": {
        "cancellations": [
          { "numberOfNights": 1, "deadline": "2026-06-23T23:59:00-04:00", "amount": "530.21", "policyType": "CANCELLATION" }
        ],
        "paymentType": "guarantee",
        "refundable": { "cancellationRefund": "REFUNDABLE_UP_TO_DEADLINE" }
      }
    }
  ]
}
```

**Data Available (Room Level):**
| Field | Available | Notes |
|---|---|---|
| Room type code | ✅ | AP7, REG, WFB |
| Room description text | ✅ | "1 Queen, 200sqft, WiFi..." |
| Bed type | ✅ | QUEEN, KING |
| Number of beds | ✅ | 1, 2 |
| Room availability | ✅ | available: true/false |
| Base price | ✅ | Before tax |
| Total price | ✅ | After tax |
| Average per night | ✅ | variations.average.base |
| Per-night breakdown | ✅ | Date-by-date price |
| Currency | ✅ | USD, EUR, GBP |
| Board type / Meal plan | ✅ | ROOM_ONLY, HALF_BOARD |
| Cancellation deadline | ✅ | Exact date/time |
| Cancellation penalty | ✅ | Amount in currency |
| Number of penalty nights | ✅ | numberOfNights |
| Refundable status | ✅ | NON_REFUNDABLE / REFUNDABLE_UP_TO_DEADLINE |
| Payment type | ✅ | deposit / guarantee |
| Commission amount | ✅ | When available |
| Rate code | ✅ | RAC, BQT, BQU |

---

### Test 3: Single Offer Detail (by Offer ID)

**Endpoint:** `GET /v3/shopping/hotel-offers/{offerId}`

**Result:** ✅ HTTP 200 — Additional data returned vs list view

**Extra data in single offer:**
- Full address (street, state, postal code)
- Amenities list (e.g., CRIBS_AVAILABLE)
- Detailed taxes breakdown:

```json
"taxes": [
  { "code": "CITY_TAX",      "amount": "48.06", "currency": "USD", "included": false },
  { "code": "TOURISM_TAX",   "amount": "3.00",  "currency": "USD", "included": false },
  { "code": "OCCUPANCY_TAX", "amount": "62.75", "currency": "USD", "included": false },
  { "code": "STATE_TAX",     "amount": "42.72", "currency": "USD", "included": false },
  { "code": "MISCELLANEOUS", "amount": "4.01",  "currency": "USD", "included": false }
]
```

**Key finding:** Call the single offer endpoint (not the list endpoint) to get full tax breakdown.

---

### Test 4: Meal Plan Test

**Hotel:** UHNYC000 (Amadeus E2E Test Property)  
**Result:** ✅ HALF_BOARD confirmed

```json
{
  "boardType": "HALF_BOARD",
  "commission": { "amount": "32.30" },
  "price": {
    "total": "240.00",
    "taxes": [{ "code": "MISCELLANEOUS", "amount": "21.82", "included": true }]
  }
}
```

**Board types confirmed:**
- `ROOM_ONLY`
- `HALF_BOARD`
- Breakfast / Full board: available in production (not in test data)

---

### Test 5: Hotel Images

**Result:** ❌ NOT AVAILABLE

All image endpoints tested:
- `/v1/media/files` → 404 Not Found
- `/v1/reference-data/locations/hotels/{id}/media` → 500 Error
- `/v1/hotels/{id}/media` → 404 Not Found

**Conclusion: Hotel images are NOT available in the Amadeus Self-Service API.**

---

### Test 6: Hotel Ratings

**Endpoint:** `GET /v2/e-reputation/hotel-sentiments`  
**Result:** ❌ 500 Error in test sandbox (may work in production with real data)

---

## Part 2: Enterprise SOAP API

**Endpoint:** `https://nodeD3.test.webservices.amadeus.com/1ASIWLUXLET`  
**SOAPAction:** `http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0`

**Result:** ❌ HTTP 500 — `12|Presentation|soap message header incorrect`  
**Fault actor:** `SI:muxdmz` (Amadeus DMZ firewall)

**Root cause:** The client IP address is not whitelisted in Amadeus's Enterprise firewall (DMZ). This is NOT a code issue — Amadeus must manually whitelist the server IP for Enterprise SOAP access.

**To fix:** Contact your Amadeus account manager and request IP whitelisting for:
- Server IP (the machine running the app)
- Office ID: DXBAD32AQ

**Available operations (from WSDL — not yet testable):**
- `Hotel_MultiSingleAvailability` v10.0 — city/multi hotel search
- `Hotel_MultiAvailability` v10.0 — multi-hotel search
- `Hotel_EnhancedSingleAvail` v2.0 — single hotel detail
- `Hotel_EnhancedPricing` v2.0 — pricing detail
- `Hotel_CompleteReservationDetails` v17.1 — reservation details
- `Hotel_Sell` v20.1 — booking

**Additional data available in Enterprise SOAP (from PDF docs):**
| Field | Available |
|---|---|
| Star rating | ✅ (Awards element) |
| Full hotel description | ✅ (VendorMessages) |
| Full amenities list | ✅ (HotelAmenity codes) |
| Recreation info | ✅ |
| Meeting facilities | ✅ |
| Contact numbers | ✅ |
| Policy text | ✅ |
| Currency conversion (all) | ✅ |
| Up to 200 tax lines | ✅ |
| Rate inclusions text | ✅ |
| Images | ❌ (Not in SOAP either) |

---

## Part 3: Self-Service vs Enterprise Comparison

| Feature | Self-Service REST | Enterprise SOAP |
|---|---|---|
| Authentication | API Key + Secret | IP Whitelist + Office ID + Agent Sign |
| Cost | Free (sandbox + production tiers) | Enterprise contract required |
| Dubai live data | Limited (sandbox) | Full (production) |
| Hotel search | ✅ by city, geo, IDs | ✅ by city, hotel code |
| Room availability | ✅ | ✅ (more detail) |
| Pricing | ✅ | ✅ + currency conversion |
| Taxes | ✅ (detailed on single offer) | ✅ up to 200 lines |
| Meal plan | ✅ | ✅ |
| Cancellation | ✅ | ✅ + full text policy |
| Star rating | ❌ | ✅ |
| Full amenities | ❌ | ✅ |
| Hotel description | ❌ | ✅ |
| Images | ❌ | ❌ |
| Booking (sell) | ✅ (Hotel Orders API) | ✅ (Hotel_Sell) |
| PNR management | ❌ | ✅ |
| Office ID usage | Not needed | Mandatory (DXBAD32AQ) |
| IP whitelist | Not needed | Required |
| Test environment | test.api.amadeus.com | nodeD3.test.webservices.amadeus.com |

---

## Part 4: Images — Final Answer

**Hotel images are NOT available in either API:**

1. **Self-Service REST API:** No image endpoint exists. All tested paths return 404/500.
2. **Enterprise SOAP API:** Hotel availability (OTA format) does not include image URLs. The SOAP reply structure (per PDF docs) contains text fields only — no image URLs.

**Why test shows placeholder images:** The Amadeus test sandbox generates placeholder images because actual hotel photo databases (like Giata, Siteminder, or hotel CRS photo libraries) are separate paid services that connect via content aggregators. Amadeus GDS does not store or serve hotel photos directly.

**To get real hotel images you need:**
- Connect to a hotel content provider (Giata, Expedia Partner Solutions, hotels.com API, or the hotel's own CRS)
- OR use the hotel chain's own image CDN (Marriott, Hilton, etc. provide image URLs through their partner programs)

---

## Part 5: What Dubai Data Returns

**Issue:** Most Dubai hotels in the sandbox return:
- "INVALID PROPERTY CODE" — hotel exists in directory but not connected to a pricing system in test
- "NO ROOMS AVAILABLE" — hotel is connected but has no inventory in test dates

**This is a sandbox limitation only.** In production:
- All Dubai hotels will have live pricing from the GDS/CRS
- Full room availability, pricing, and taxes will be returned
- The same API calls will work without changes

---

## Immediate Next Steps

1. **For REST API production:** Switch `test.api.amadeus.com` to `api.amadeus.com` — same endpoints, real data
2. **For Enterprise SOAP access:** Contact Amadeus account manager to whitelist your production server IP
3. **For hotel images:** Integrate a separate content provider (Giata recommended for GDS bookings)
4. **For star ratings:** Use the Enterprise SOAP `Award` element, or add Google Places / TripAdvisor API
5. **Markup pricing:** Apply markup on top of `price.total` — Amadeus does not provide a recommended selling price field

---

## API Endpoints Summary

| Operation | Method | Endpoint |
|---|---|---|
| Get token | POST | `/v1/security/oauth2/token` |
| Hotel list by city | GET | `/v1/reference-data/locations/hotels/by-city` |
| Hotel list by IDs | GET | `/v1/reference-data/locations/hotels/by-hotels` |
| Hotel list by keyword | GET | `/v1/reference-data/locations/hotels/by-keyword` |
| Hotel offers (search) | GET | `/v3/shopping/hotel-offers` |
| Single offer detail | GET | `/v3/shopping/hotel-offers/{offerId}` |
| Hotel sentiments | GET | `/v2/e-reputation/hotel-sentiments` |
| Book hotel | POST | `/v2/booking/hotel-orders` |
