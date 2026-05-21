from flask import Flask, render_template, request, jsonify, redirect
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
    f"https://nodeD3.production.webservices.amadeus.com/{SOAP_ACCESS_POINT}",
)

AVAILABILITY_ACTION = "http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0"
PRICING_ACTION = "http://webservices.amadeus.com/Hotel_EnhancedPricing_2.0"
CONTENT_ACTION = "http://webservices.amadeus.com/OTA_HotelDescriptiveInfoRQ_07.1_1A2007A"

_offer_detail_cache = {}
_hotel_image_cache = {}

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

def build_start_envelope(action, body_xml):
    message_id = str(uuid.uuid4())
    password_digest, nonce_b64, created = amadeus_password_digest(SOAP_PASSWORD or "")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ses="http://xml.amadeus.com/2010/06/Session_v3">
  <soap:Header>
    <ses:Session TransactionStatusCode="Start"/>
    <add:MessageID xmlns:add="http://www.w3.org/2005/08/addressing">{escape(message_id)}</add:MessageID>
    <add:Action xmlns:add="http://www.w3.org/2005/08/addressing">{escape(action)}</add:Action>
    <add:To xmlns:add="http://www.w3.org/2005/08/addressing">{escape(SOAP_ENDPOINT)}</add:To>
    <link:TransactionFlowLink xmlns:link="http://wsdl.amadeus.com/2010/06/ws/Link_v1"/>
    <oas:Security xmlns:oas="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <oas:UsernameToken xmlns:oas1="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd" oas1:Id="UsernameToken-1">
        <oas:Username>{escape(SOAP_USER_ID or "")}</oas:Username>
        <oas:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</oas:Nonce>
        <oas:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{password_digest}</oas:Password>
        <oas1:Created>{created}</oas1:Created>
      </oas:UsernameToken>
    </oas:Security>
    <AMA_SecurityHostedUser xmlns="http://xml.amadeus.com/2010/06/Security_v1">
      <UserID AgentDutyCode="{escape(SOAP_AGENT_DUTY)}" POS_Type="1" PseudoCityCode="{escape(SOAP_OFFICE_ID)}" RequestorType="U"/>
    </AMA_SecurityHostedUser>
  </soap:Header>
  <soap:Body>
{body_xml}
  </soap:Body>
</soap:Envelope>"""


def build_inseries_envelope(action, body_xml, soap_session):
    message_id = str(uuid.uuid4())
    try:
        sequence = str(int(soap_session.get("sequence_number") or "1") + 1)
    except ValueError:
        sequence = soap_session.get("sequence_number") or "2"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ses="http://xml.amadeus.com/2010/06/Session_v3">
  <soap:Header>
    <ses:Session TransactionStatusCode="InSeries">
      <ses:SessionId>{escape(soap_session.get("session_id", ""))}</ses:SessionId>
      <ses:SequenceNumber>{escape(sequence)}</ses:SequenceNumber>
      <ses:SecurityToken>{escape(soap_session.get("security_token", ""))}</ses:SecurityToken>
    </ses:Session>
    <add:MessageID xmlns:add="http://www.w3.org/2005/08/addressing">{escape(message_id)}</add:MessageID>
    <add:Action xmlns:add="http://www.w3.org/2005/08/addressing">{escape(action)}</add:Action>
    <add:To xmlns:add="http://www.w3.org/2005/08/addressing">{escape(SOAP_ENDPOINT)}</add:To>
    <link:TransactionFlowLink xmlns:link="http://wsdl.amadeus.com/2010/06/ws/Link_v1"/>
  </soap:Header>
  <soap:Body>
{body_xml}
  </soap:Body>
</soap:Envelope>"""


def build_availability_body(city, checkin, checkout, adults, rooms=1):
    return f"""    <OTA_HotelAvailRQ EchoToken="WebsiteSearch" Version="4.000" PrimaryLangID="EN"
      SummaryOnly="true" RateRangeOnly="true" ExactMatchOnly="false" SearchCacheLevel="Live"
      RateDetailsInd="true" RequestedCurrency="AED">
      <AvailRequestSegments><AvailRequestSegment InfoSource="Distribution">
        <HotelSearchCriteria AvailableOnlyIndicator="true"><Criterion ExactMatch="true">
          <HotelRef HotelCityCode="{escape(city)}"/>
          <StayDateRange Start="{escape(checkin)}" End="{escape(checkout)}"/>
          <RoomStayCandidates><RoomStayCandidate Quantity="{int(rooms)}"><GuestCounts IsPerRoom="true">
            <GuestCount AgeQualifyingCode="10" Count="{int(adults)}"/>
          </GuestCounts></RoomStayCandidate></RoomStayCandidates>
        </Criterion></HotelSearchCriteria>
      </AvailRequestSegment></AvailRequestSegments>
    </OTA_HotelAvailRQ>"""


def build_pricing_body(offer):
    return f"""    <OTA_HotelAvailRQ EchoToken="WebsitePricing" Version="4.000" PrimaryLangID="EN"
      SummaryOnly="false" RateRangeOnly="false" AvailRatesOnly="true" RequestedCurrency="AED">
      <AvailRequestSegments><AvailRequestSegment InfoSource="Distribution">
        <HotelSearchCriteria><Criterion ExactMatch="true">
          <HotelRef HotelCode="{escape(offer.get("hotelId", ""))}"/>
          <StayDateRange Start="{escape(offer.get("checkin", ""))}" End="{escape(offer.get("checkout", ""))}"/>
          <RatePlanCandidates><RatePlanCandidate RatePlanCode="{escape(offer.get("ratePlanCode", ""))}"/></RatePlanCandidates>
          <RoomStayCandidates><RoomStayCandidate RoomTypeCode="{escape(offer.get("roomTypeCode", ""))}" BookingCode="{escape(offer.get("bookingCode", ""))}" Quantity="{int(offer.get("rooms") or 1)}">
            <GuestCounts IsPerRoom="true"><GuestCount AgeQualifyingCode="10" Count="{int(offer.get("adults") or 1)}"/></GuestCounts>
          </RoomStayCandidate></RoomStayCandidates>
        </Criterion></HotelSearchCriteria>
      </AvailRequestSegment></AvailRequestSegments>
    </OTA_HotelAvailRQ>"""


def build_hotel_content_body(hotel_code):
    return f"""    <OTA_HotelDescriptiveInfoRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="WebsiteImages" Version="6.001" PrimaryLangID="en">
      <HotelDescriptiveInfos>
        <HotelDescriptiveInfo HotelCode="{escape(hotel_code)}">
          <HotelInfo SendData="true"/>
          <FacilityInfo SendGuestRooms="true"/>
          <Policies SendPolicies="true"/>
          <AreaInfo SendRefPoints="true"/>
          <ContactInfo SendData="true"/>
          <MultimediaObjects SendData="true"/>
        </HotelDescriptiveInfo>
      </HotelDescriptiveInfos>
    </OTA_HotelDescriptiveInfoRQ>"""


def parse_hotel_images(xml_text, limit=12):
    root = ET.fromstring(xml_text)
    images = []
    seen = set()
    preferred = {"J": 0, "I": 1, "H": 2, "F": 3, "E": 4, "D": 5, "C": 6, "B": 7, "A": 8}
    for image_item in root.iter():
        if local_name(image_item.tag) != "ImageItem":
            continue
        candidates = []
        for image_format in image_item.iter():
            if local_name(image_format.tag) != "ImageFormat":
                continue
            url_node = first_child(image_format, "URL")
            url = text_of(url_node)
            if not url or not url.lower().startswith(("http://", "https://")):
                continue
            width = int(image_format.get("Width") or 0)
            height = int(image_format.get("Height") or 0)
            dimension = image_format.get("DimensionCategory") or ("ORIGINAL" if image_format.get("IsOriginalIndicator") else "")
            rank = preferred.get(dimension, 20 if dimension == "ORIGINAL" else 15)
            candidates.append((rank, -width, {
                "url": url,
                "width": width,
                "height": height,
                "category": image_item.get("Category", ""),
                "dimension": dimension,
            }))
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            image = candidates[0][2]
            if image["url"] not in seen:
                seen.add(image["url"])
                images.append(image)
        if len(images) >= limit:
            break
    return images


def get_hotel_images(hotel_code):
    if not hotel_code:
        return []
    if hotel_code in _hotel_image_cache:
        return _hotel_image_cache[hotel_code]
    try:
        envelope = build_start_envelope(CONTENT_ACTION, build_hotel_content_body(hotel_code))
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            SOAP_ENDPOINT,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": CONTENT_ACTION},
            timeout=45,
        )
        if response.status_code >= 400:
            _hotel_image_cache[hotel_code] = []
        else:
            _hotel_image_cache[hotel_code] = parse_hotel_images(response.text)
    except Exception as exc:
        print(f"Hotel image fetch failed for {hotel_code}: {exc}", flush=True)
        _hotel_image_cache[hotel_code] = []
    return _hotel_image_cache[hotel_code]

def call_hotel_availability(city, checkin, checkout, adults, rooms=1):
    require_soap_config()
    print(
        f"SOAP search request: city={city}, checkin={checkin}, checkout={checkout}, adults={adults}, rooms={rooms}",
        flush=True,
    )
    envelope = build_start_envelope(AVAILABILITY_ACTION, build_availability_body(city, checkin, checkout, adults, rooms))
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        SOAP_ENDPOINT,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": AVAILABILITY_ACTION,
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
    parsed = parse_hotel_availability_response(response.text, city, checkin, checkout, adults, rooms)
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
    soap_session = parse_session(root)
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

def parse_session(root):
    soap_session = {}
    session_node = first_desc(root, "Session")
    if session_node is None:
        return soap_session
    for child in list(session_node):
        name = local_name(child.tag)
        value = text_of(child)
        if name == "SessionId":
            soap_session["session_id"] = value
        elif name == "SequenceNumber":
            soap_session["sequence_number"] = value
        elif name == "SecurityToken":
            soap_session["security_token"] = value
    return soap_session


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

def parse_offer(room_stay, hotel_id, city="", checkin="", checkout="", adults=1, rooms=1, soap_session=None):
    room_type = first_desc(room_stay, "RoomType")
    rate_plan = first_desc(room_stay, "RatePlan")
    room_rate = first_desc(room_stay, "RoomRate")
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
        "hotelId": hotel_id,
        "city": city,
        "roomTypeCode": room_rate.get("RoomTypeCode", "") if room_rate is not None else (room_type.get("RoomTypeCode", "") if room_type is not None else ""),
        "ratePlanCode": room_rate.get("RatePlanCode", "") if room_rate is not None else (rate_plan.get("RatePlanCode", "") if rate_plan is not None else ""),
        "bookingCode": room_rate.get("BookingCode", "") if room_rate is not None else "",
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "rooms": rooms,
        "session": soap_session or {},
    }
    return {
        "offerId": offer_id,
        "roomType": room_rate.get("RoomTypeCode", "") if room_rate is not None else (room_type.get("RoomTypeCode", "") if room_type is not None else ""),
        "description": (description or room_desc)[:120],
        "beds": room_type.get("NumberOfUnits", "") if room_type is not None else "",
        "bedType": room_type.get("RoomType", "") if room_type is not None else "",
        "boardType": (rate_plan.get("MealsIncluded") if rate_plan is not None else "") or "ROOM_ONLY",
        "basePrice": base_money.get("amount") or "",
        "totalPrice": total_money.get("amount") or base_money.get("amount") or "",
        "avgPerNight": base_money.get("amount") or total_money.get("amount") or "",
        "currency": total_money.get("currency") or base_money.get("currency") or "USD",
        "paymentType": "",
        "bookingCode": room_rate.get("BookingCode", "") if room_rate is not None else "",
        "ratePlanCode": room_rate.get("RatePlanCode", "") if room_rate is not None else (rate_plan.get("RatePlanCode", "") if rate_plan is not None else ""),
        "refundable": "REFUNDABLE_UP_TO_DEADLINE" if deadline is not None else "",
        "cancelDeadline": deadline.get("AbsoluteDeadline", "") if deadline is not None else "",
        "cancelAmount": cancel_money.get("amount") or "",
    }

def parse_hotel_availability_response(xml_text, city, checkin="", checkout="", adults=1, rooms=1):
    root = ET.fromstring(xml_text)
    soap_session = parse_session(root)
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
    rph_to_hotel_id = {}

    for hotel_stay in root.iter():
        if local_name(hotel_stay.tag) != "HotelStay":
            continue
        prop = first_desc(hotel_stay, "BasicPropertyInfo")
        hotel = parse_property(prop, city)
        hotel_id = hotel["hotelId"]
        if not hotel_id:
            continue
        hotels[hotel_id] = hotel
        for rph in (hotel_stay.get("RoomStayRPH") or "").split():
            rph_to_hotel_id[rph] = hotel_id

    for room_stay in root.iter():
        if local_name(room_stay.tag) != "RoomStay":
            continue
        prop = first_desc(room_stay, "BasicPropertyInfo")
        hotel = parse_property(prop, city)
        hotel_id = hotel["hotelId"] or rph_to_hotel_id.get(room_stay.get("RPH", ""), "")
        if not hotel_id:
            ref = first_desc(room_stay, "Reference")
            hotel_id = ref.get("ID") if ref is not None else ""
        if not hotel_id:
            continue
        hotels.setdefault(hotel_id, hotel if hotel["hotelId"] else {
            "hotelId": hotel_id,
            "name": "",
            "chainCode": "",
            "city": city,
            "latitude": None,
            "longitude": None,
            "address": "",
            "country": "",
            "available": False,
            "offers": [],
        })
        offer = parse_offer(room_stay, hotel_id, city, checkin, checkout, adults, rooms, soap_session)
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

def call_enhanced_pricing(offer_id):
    cached = _offer_detail_cache.get(offer_id)
    if not cached:
        return {"taxes": [], "description": "", "amenities": [], "address": {}, "images": []}
    cached["images"] = get_hotel_images(cached.get("hotelId", ""))
    required = ("hotelId", "roomTypeCode", "ratePlanCode", "bookingCode", "checkin", "checkout")
    if not all(cached.get(key) for key in required):
        return cached
    soap_session = cached.get("session") or {}
    if not soap_session.get("session_id") or not soap_session.get("security_token"):
        return cached
    envelope = build_inseries_envelope(PRICING_ACTION, build_pricing_body(cached), soap_session)
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        SOAP_ENDPOINT,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": PRICING_ACTION},
        timeout=45,
    )
    if response.status_code >= 400:
        cached["pricingStatus"] = f"HTTP {response.status_code}"
        cached["pricingFault"] = parse_soap_fault(response.text)
        return cached
    parsed = parse_hotel_availability_response(
        response.text,
        cached.get("city", ""),
        cached.get("checkin", ""),
        cached.get("checkout", ""),
        cached.get("adults", 1),
        cached.get("rooms", 1),
    )
    priced_offer = None
    for hotel in parsed.get("hotels", []):
        offers = hotel.get("offers") or []
        if offers:
            priced_offer = offers[0]
            break
    if priced_offer:
        cached["pricingStatus"] = "SUCCESS"
        cached["pricedOffer"] = priced_offer
        cached["taxes"] = _offer_detail_cache.get(priced_offer.get("offerId"), {}).get("taxes", cached.get("taxes", []))
        cached["description"] = priced_offer.get("description") or cached.get("description", "")
    else:
        cached["pricingStatus"] = parsed.get("message", "No priced offer returned")
    return cached


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/search-hotels")
def search_hotels():
    city      = request.args.get("city", "DXB").upper()
    checkin   = request.args.get("checkin")
    checkout  = request.args.get("checkout")
    adults    = request.args.get("adults", 2)
    rooms     = request.args.get("rooms", 1)
    try:
        data, status = call_hotel_availability(city, checkin, checkout, adults, rooms)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"SOAP request failed: {exc}"}), 502
    return jsonify(data), status

@app.route("/api/hotel-images/<hotel_id>")
def hotel_images(hotel_id):
    return jsonify({"hotelId": hotel_id, "images": get_hotel_images(hotel_id)})


@app.route("/api/hotel-image/<hotel_id>")
def hotel_image(hotel_id):
    images = get_hotel_images(hotel_id)
    if not images:
        return ("", 204)
    return redirect(images[0]["url"], code=302)


@app.route("/api/offer-detail/<offer_id>")
def offer_detail(offer_id):
    return jsonify(call_enhanced_pricing(offer_id))

if __name__ == "__main__":
    app.run(debug=True, port=5050, threaded=True)

