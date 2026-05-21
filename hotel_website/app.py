from flask import Flask, render_template, request, jsonify
import os
import requests
import uuid
import base64
import hashlib
import secrets
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SOAP_ACCESS_POINT = os.environ.get("AMADEUS_WEB_SERVICE_ACCESS_POINT", "1ASIWLUXLET")
SOAP_USER_ID      = os.environ.get("AMADEUS_USER_ID")
SOAP_PASSWORD     = os.environ.get("AMADEUS_CLEAR_PASSWORD") or os.environ.get("BASE64_PWD")
SOAP_OFFICE_ID    = os.environ.get("AMADEUS_OFFICE_ID", "DXBAD32AQ")
SOAP_AGENT_DUTY   = os.environ.get("AMADEUS_AGENT_DUTY_CODE", "SU")
SOAP_ENDPOINT     = os.environ.get(
    "AMADEUS_SOAP_ENDPOINT",
    f"https://nodeD3.test.webservices.amadeus.com/{SOAP_ACCESS_POINT}",
)

_offer_detail_cache = {}

NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "ota": "http://www.opentravel.org/OTA/2003/05",
}

def local_name(tag):
    return tag.rsplit("}", 1)[-1]

def children_named(node, name):
    return [child for child in list(node) if local_name(child.tag) == name]

def first_child(node, name):
    for child in list(node):
        if local_name(child.tag) == name:
            return child
    return None

def first_desc(node, name):
    for child in node.iter():
        if local_name(child.tag) == name:
            return child
    return None

def text_of(node):
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def money_attrs(node):
    if node is None:
        return {}
    return {
        "amount": node.get("AmountAfterTax") or node.get("AmountBeforeTax") or node.get("Amount"),
        "currency": node.get("CurrencyCode") or node.get("Currency"),
    }

def require_soap_config():
    if not SOAP_USER_ID or not SOAP_PASSWORD:
        raise RuntimeError(
            "Set AMADEUS_USER_ID and AMADEUS_CLEAR_PASSWORD in .env before calling SOAP APIs."
        )

def amadeus_password_digest(password):
    nonce = secrets.token_bytes(16)
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S:000Z")
    password_sha1 = hashlib.sha1(password.encode("utf-8")).digest()
    digest = hashlib.sha1(nonce + created.encode("utf-8") + password_sha1).digest()
    return base64.b64encode(digest).decode("ascii"), nonce_b64, created

def build_soap_envelope(city, checkin, checkout, adults):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    echo = str(uuid.uuid4())
    message_id = f"urn:uuid:{uuid.uuid4()}"
    password_digest, nonce_b64, created = amadeus_password_digest(SOAP_PASSWORD or "")
    city = escape(city)
    user_id = escape(SOAP_USER_ID or "")
    office_id = escape(SOAP_OFFICE_ID or "")
    agent_duty = escape(SOAP_AGENT_DUTY)
    endpoint = escape(SOAP_ENDPOINT)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
  xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:ota="http://www.opentravel.org/OTA/2003/05"
  xmlns:awsse="http://xml.amadeus.com/2010/06/Session_v3"
  xmlns:awsl="http://wsdl.amadeus.com/2010/06/ws/Link_v1"
  xmlns:amasec="http://xml.amadeus.com/2010/06/Security_v1"
  xmlns:wsa="http://www.w3.org/2005/08/addressing"
  xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
  xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
  <soapenv:Header>
    <wsa:MessageID>{message_id}</wsa:MessageID>
    <wsa:Action>http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0</wsa:Action>
    <wsa:To>{endpoint}</wsa:To>
    <awsse:Session TransactionStatusCode="Start"/>
    <awsl:TransactionFlowLink>
      <awsl:Consumer>
        <awsl:UniqueID>{echo}</awsl:UniqueID>
      </awsl:Consumer>
    </awsl:TransactionFlowLink>
    <amasec:AMA_SecurityHostedUser>
      <amasec:UserID AgentDutyCode="{agent_duty}" POS_Type="1" PseudoCityCode="{office_id}" RequestorType="U"/>
    </amasec:AMA_SecurityHostedUser>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>{user_id}</wsse:Username>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</wsse:Password>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ota:OTA_HotelAvailRQ EchoToken="{echo}" TimeStamp="{now}" Version="4.000"
      PrimaryLangID="EN" SummaryOnly="false" AvailRatesOnly="true" BestOnly="true">
      <ota:POS>
        <ota:Source>
          <ota:RequestorID ID="{user_id}" Type="5"/>
          <ota:BookingChannel Type="7"/>
        </ota:Source>
      </ota:POS>
      <ota:AvailRequestSegments>
        <ota:AvailRequestSegment>
          <ota:HotelSearchCriteria AvailableOnlyIndicator="true">
            <ota:Criterion>
              <ota:HotelRef HotelCityCode="{city}" HotelCodeContext="1A"/>
              <ota:StayDateRange Start="{escape(checkin)}" End="{escape(checkout)}"/>
              <ota:RoomStayCandidates>
                <ota:RoomStayCandidate Quantity="1">
                  <ota:GuestCounts>
                    <ota:GuestCount AgeQualifyingCode="10" Count="{int(adults)}"/>
                  </ota:GuestCounts>
                </ota:RoomStayCandidate>
              </ota:RoomStayCandidates>
            </ota:Criterion>
          </ota:HotelSearchCriteria>
        </ota:AvailRequestSegment>
      </ota:AvailRequestSegments>
    </ota:OTA_HotelAvailRQ>
  </soapenv:Body>
</soapenv:Envelope>"""

def call_hotel_availability(city, checkin, checkout, adults):
    require_soap_config()
    print(
        f"SOAP search request: city={city}, checkin={checkin}, checkout={checkout}, adults={adults}",
        flush=True,
    )
    envelope = build_soap_envelope(city, checkin, checkout, adults)
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        SOAP_ENDPOINT,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0",
        },
        timeout=45,
    )
    if response.status_code >= 400:
        fault = parse_soap_fault(response.text)
        print(
            f"SOAP search failed: http_status={response.status_code}, fault={fault or 'N/A'}",
            flush=True,
        )
        log_soap_fault_explanation(fault)
        return {"error": {"status": response.status_code, "fault": fault, "body": response.text[:2000]}}, 502
    print(f"SOAP search succeeded: http_status={response.status_code}", flush=True)
    parsed = parse_hotel_availability_response(response.text, city)
    if not parsed.get("hotels"):
        dump_path = os.path.join(os.path.dirname(__file__), "last_empty_response.xml")
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        root = ET.fromstring(response.text) if response.text.strip().startswith("<") else None
        top_tags = sorted({local_name(n.tag) for n in (root.iter() if root is not None else [])})
        print(
            f"SOAP empty-result diagnostic: bytes={len(response.text)}, "
            f"dump={dump_path}, unique_tags={top_tags[:40]}",
            flush=True,
        )
    return parsed, 200

def parse_soap_fault(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    fault = first_desc(root, "Fault")
    if fault is None:
        return ""
    return text_of(first_child(fault, "faultstring")) or text_of(fault)

def log_soap_fault_explanation(fault):
    if fault != "11|Session|":
        return
    print(
        "\n".join([
            "SOAP fault explanation:",
            "  11|Session| means Amadeus accepted the SOAP request format but rejected the session context.",
            "  This is usually caused by an incorrect or inactive Enterprise SOAP account setup, not by the website UI.",
            "  Verify these values with Amadeus:",
            f"    AMADEUS_WEB_SERVICE_ACCESS_POINT={SOAP_ACCESS_POINT}",
            f"    AMADEUS_USER_ID={SOAP_USER_ID or 'MISSING'}",
            f"    AMADEUS_OFFICE_ID={SOAP_OFFICE_ID}",
            f"    AMADEUS_AGENT_DUTY_CODE={SOAP_AGENT_DUTY}",
            "    SOAP 4.0 access enabled for this user",
            "    WSAP assigned to this user",
            "    Current public IP whitelisted for Enterprise SOAP test access",
            
        ]),
        flush=True,
    )

def parse_address(address_node):
    if address_node is None:
        return ""
    lines = []
    for name in ("AddressLine", "StreetNmbr", "CityName", "PostalCode"):
        value = text_of(first_child(address_node, name))
        if value:
            lines.append(value)
    return " ".join(lines)

def parse_property(prop, city):
    if prop is None:
        return {
            "hotelId": "",
            "name": "",
            "chainCode": "",
            "city": city,
            "latitude": None,
            "longitude": None,
            "address": "",
            "country": "",
            "available": False,
            "offers": [],
        }
    position = first_child(prop, "Position")
    address = first_child(prop, "Address")
    country = first_child(address, "CountryName") if address is not None else None
    return {
        "hotelId": prop.get("HotelCode", ""),
        "name": prop.get("HotelName", ""),
        "chainCode": prop.get("ChainCode", ""),
        "city": prop.get("HotelCityCode", city),
        "latitude": position.get("Latitude") if position is not None else None,
        "longitude": position.get("Longitude") if position is not None else None,
        "address": parse_address(address),
        "country": country.get("Code", "") if country is not None else "",
        "available": False,
        "offers": [],
    }

def parse_offer(room_stay, hotel_id):
    room_type = first_desc(room_stay, "RoomType")
    rate_plan = first_desc(room_stay, "RatePlan")
    total = first_child(room_stay, "Total") or first_desc(room_stay, "Total")
    base = first_desc(room_stay, "Base")
    cancel = first_desc(room_stay, "CancelPenalty")
    deadline = first_child(cancel, "Deadline") if cancel is not None else None
    penalty = first_child(cancel, "AmountPercent") if cancel is not None else None
    description = text_of(first_desc(room_stay, "RoomRateDescription")) or text_of(first_desc(room_stay, "RatePlanDescription"))
    room_desc = text_of(first_desc(room_stay, "RoomDescription"))
    total_money = money_attrs(total)
    base_money = money_attrs(base)
    cancel_money = money_attrs(penalty)
    offer_id = f"{hotel_id or 'hotel'}-{uuid.uuid4().hex[:10]}"
    taxes = []
    for tax in room_stay.iter():
        if local_name(tax.tag) == "Tax":
            taxes.append({
                "code": tax.get("Type") or tax.get("Code") or "TAX",
                "amount": tax.get("Amount"),
                "currency": tax.get("CurrencyCode") or total_money.get("currency") or base_money.get("currency"),
                "included": (tax.get("ChargeUnit") or "").lower() != "extra",
            })
    _offer_detail_cache[offer_id] = {
        "taxes": taxes,
        "description": description or room_desc,
        "amenities": [],
        "address": {},
    }
    return {
        "offerId": offer_id,
        "roomType": room_type.get("RoomTypeCode", "") if room_type is not None else "",
        "description": (description or room_desc)[:120],
        "beds": room_type.get("NumberOfUnits", "") if room_type is not None else "",
        "bedType": room_type.get("RoomType", "") if room_type is not None else "",
        "boardType": (rate_plan.get("MealsIncluded") if rate_plan is not None else "") or "ROOM_ONLY",
        "basePrice": base_money.get("amount") or "",
        "totalPrice": total_money.get("amount") or base_money.get("amount") or "",
        "avgPerNight": base_money.get("amount") or total_money.get("amount") or "",
        "currency": total_money.get("currency") or base_money.get("currency") or "USD",
        "paymentType": "",
        "refundable": "REFUNDABLE_UP_TO_DEADLINE" if deadline is not None else "",
        "cancelDeadline": deadline.get("AbsoluteDeadline", "") if deadline is not None else "",
        "cancelAmount": cancel_money.get("amount") or "",
    }

def parse_hotel_availability_response(xml_text, city):
    root = ET.fromstring(xml_text)
    fault = first_desc(root, "Fault")
    if fault is not None:
        return {"error": {"message": text_of(fault)}}

    def describe_error(node):
        text = text_of(node)
        if text:
            return text
        bits = []
        for attr in ("ShortText", "Code", "Type", "Status", "RecordID"):
            value = node.get(attr)
            if value:
                bits.append(f"{attr}={value}")
        return ", ".join(bits)

    errors = [describe_error(node) for node in root.iter() if local_name(node.tag) in ("Error", "Warning")]
    errors = [e for e in errors if e]
    hotels = {}

    for hotel_stay in root.iter():
        if local_name(hotel_stay.tag) != "HotelStay":
            continue
        prop = first_desc(hotel_stay, "BasicPropertyInfo")
        hotel = parse_property(prop, city)
        if hotel["hotelId"]:
            hotels[hotel["hotelId"]] = hotel

    for room_stay in root.iter():
        if local_name(room_stay.tag) != "RoomStay":
            continue
        prop = first_desc(room_stay, "BasicPropertyInfo")
        hotel = parse_property(prop, city)
        hotel_id = hotel["hotelId"]
        if not hotel_id:
            ref = first_desc(room_stay, "Reference")
            hotel_id = ref.get("ID") if ref is not None else ""
            hotel["hotelId"] = hotel_id
        if not hotel_id:
            continue
        hotels.setdefault(hotel_id, hotel)
        offer = parse_offer(room_stay, hotel_id)
        hotels[hotel_id]["offers"].append(offer)
        hotels[hotel_id]["available"] = True
        for key, value in hotel.items():
            if value and not hotels[hotel_id].get(key):
                hotels[hotel_id][key] = value

    result = list(hotels.values())
    if not result and errors:
        return {"hotels": [], "message": " ".join(errors[:3])}
    if not result:
        return {"hotels": [], "message": "No hotels found for this city/date search."}
    available = [h for h in result if h["available"]]
    unavailable = [h for h in result if not h["available"]]
    return {"hotels": available + unavailable}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/search-hotels")
def search_hotels():
    city      = request.args.get("city", "DXB").upper()
    checkin   = request.args.get("checkin")
    checkout  = request.args.get("checkout")
    adults    = request.args.get("adults", 2)
    try:
        data, status = call_hotel_availability(city, checkin, checkout, adults)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"SOAP request failed: {exc}"}), 502
    return jsonify(data), status

@app.route("/api/offer-detail/<offer_id>")
def offer_detail(offer_id):
    return jsonify(_offer_detail_cache.get(offer_id, {
        "taxes": [],
        "description": "",
        "amenities": [],
        "address": {},
    }))

if __name__ == "__main__":
    app.run(debug=True, port=5050)
