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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

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

TBO_BASE_URL  = os.environ.get("TBO_BASE_URL", "https://apiwr.tboholidays.com/HotelAPI")
TBO_USERNAME  = os.environ.get("TBO_USERNAME")
TBO_PASSWORD  = os.environ.get("TBO_PASSWORD")

AMADEUS_REST_BASE   = os.environ.get("AMADEUS_REST_BASE", "https://test.api.amadeus.com")
AMADEUS_API_KEY     = os.environ.get("AMADEUS_API_KEY")
AMADEUS_API_SECRET  = os.environ.get("AMADEUS_API_SECRET")
_amadeus_rest_token = {"value": None, "expires_at": 0}

IATA_CITY_INDEX = [
    {"code": "DXB", "name": "Dubai", "country": "United Arab Emirates"},
    {"code": "AUH", "name": "Abu Dhabi", "country": "United Arab Emirates"},
    {"code": "DOH", "name": "Doha", "country": "Qatar"},
    {"code": "RUH", "name": "Riyadh", "country": "Saudi Arabia"},
    {"code": "JED", "name": "Jeddah", "country": "Saudi Arabia"},
    {"code": "CAI", "name": "Cairo", "country": "Egypt"},
    {"code": "IST", "name": "Istanbul", "country": "Turkey"},
    {"code": "LHR", "name": "London", "country": "United Kingdom"},
    {"code": "CDG", "name": "Paris", "country": "France"},
    {"code": "BCN", "name": "Barcelona", "country": "Spain"},
    {"code": "MAD", "name": "Madrid", "country": "Spain"},
    {"code": "FCO", "name": "Rome", "country": "Italy"},
    {"code": "MXP", "name": "Milan", "country": "Italy"},
    {"code": "FRA", "name": "Frankfurt", "country": "Germany"},
    {"code": "MUC", "name": "Munich", "country": "Germany"},
    {"code": "BER", "name": "Berlin", "country": "Germany"},
    {"code": "AMS", "name": "Amsterdam", "country": "Netherlands"},
    {"code": "ZRH", "name": "Zurich", "country": "Switzerland"},
    {"code": "VIE", "name": "Vienna", "country": "Austria"},
    {"code": "ATH", "name": "Athens", "country": "Greece"},
    {"code": "JFK", "name": "New York", "country": "United States"},
    {"code": "LAX", "name": "Los Angeles", "country": "United States"},
    {"code": "MIA", "name": "Miami", "country": "United States"},
    {"code": "ORD", "name": "Chicago", "country": "United States"},
    {"code": "SFO", "name": "San Francisco", "country": "United States"},
    {"code": "LAS", "name": "Las Vegas", "country": "United States"},
    {"code": "YYZ", "name": "Toronto", "country": "Canada"},
    {"code": "YVR", "name": "Vancouver", "country": "Canada"},
    {"code": "BOM", "name": "Mumbai", "country": "India"},
    {"code": "DEL", "name": "New Delhi", "country": "India"},
    {"code": "BLR", "name": "Bangalore", "country": "India"},
    {"code": "MAA", "name": "Chennai", "country": "India"},
    {"code": "CMB", "name": "Colombo", "country": "Sri Lanka"},
    {"code": "SIN", "name": "Singapore", "country": "Singapore"},
    {"code": "BKK", "name": "Bangkok", "country": "Thailand"},
    {"code": "HKT", "name": "Phuket", "country": "Thailand"},
    {"code": "KUL", "name": "Kuala Lumpur", "country": "Malaysia"},
    {"code": "CGK", "name": "Jakarta", "country": "Indonesia"},
    {"code": "DPS", "name": "Bali (Denpasar)", "country": "Indonesia"},
    {"code": "HKG", "name": "Hong Kong", "country": "Hong Kong"},
    {"code": "ICN", "name": "Seoul", "country": "South Korea"},
    {"code": "NRT", "name": "Tokyo", "country": "Japan"},
    {"code": "PEK", "name": "Beijing", "country": "China"},
    {"code": "PVG", "name": "Shanghai", "country": "China"},
    {"code": "SYD", "name": "Sydney", "country": "Australia"},
    {"code": "MEL", "name": "Melbourne", "country": "Australia"},
    {"code": "AKL", "name": "Auckland", "country": "New Zealand"},
    {"code": "JNB", "name": "Johannesburg", "country": "South Africa"},
    {"code": "CPT", "name": "Cape Town", "country": "South Africa"},
    {"code": "NBO", "name": "Nairobi", "country": "Kenya"},
    {"code": "GRU", "name": "Sao Paulo", "country": "Brazil"},
    {"code": "MEX", "name": "Mexico City", "country": "Mexico"},
]
_last_hotel_name_index = {}

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


def build_availability_body(city, checkin, checkout, adults, rooms=1, hotel_code=""):
    hotel_ref = (
        f'<HotelRef HotelCode="{escape(hotel_code)}"/>'
        if hotel_code
        else f'<HotelRef HotelCityCode="{escape(city)}"/>'
    )
    return f"""    <OTA_HotelAvailRQ EchoToken="WebsiteSearch" Version="4.000" PrimaryLangID="EN"
      SummaryOnly="true" RateRangeOnly="true" ExactMatchOnly="false" SearchCacheLevel="Live"
      RateDetailsInd="true" RequestedCurrency="AED">
      <AvailRequestSegments><AvailRequestSegment InfoSource="Distribution">
        <HotelSearchCriteria AvailableOnlyIndicator="true"><Criterion ExactMatch="true">
          {hotel_ref}
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


def parse_hotel_images(xml_text, limit=12, include_description=False):
    root = ET.fromstring(xml_text)
    images = []
    seen = set()
    preferred = {"J": 0, "I": 1, "H": 2, "F": 3, "E": 4, "D": 5, "C": 6, "B": 7, "A": 8}

    def add_image(url, width=0, height=0, category="", dimension="", description=""):
        if not url or not url.lower().startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        entry = {
            "url": url,
            "width": width,
            "height": height,
            "category": category,
            "dimension": dimension,
        }
        if include_description:
            entry["description"] = description
        images.append(entry)

    for image_item in root.iter():
        if local_name(image_item.tag) != "ImageItem":
            continue
        desc_node = first_desc(image_item, "Description") if include_description else None
        item_desc = text_of(desc_node) if desc_node is not None else ""
        candidates = []
        for image_format in image_item.iter():
            if local_name(image_format.tag) != "ImageFormat":
                continue
            url_node = first_desc(image_format, "URL")
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
                "description": item_desc,
            }))
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            add_image(**candidates[0][2])
        else:
            urls = []
            for url_node in image_item.iter():
                if local_name(url_node.tag) == "URL":
                    url = text_of(url_node)
                    if url and url.lower().startswith(("http://", "https://")):
                        urls.append(url)
            if urls:
                add_image(urls[-1], category=image_item.get("Category", ""), description=item_desc)
        if len(images) >= limit:
            break
    return images


# Amadeus image categories (1A standard):
# 1 Exterior · 2 Lobby · 3 Pool · 4 Restaurant · 5 Health Club · 6 Guest Room
# 7 Suite · 8 Sports · 9 Bar · 10 Beach · 11 Spa · 12 Suite · 13 Meeting · 17 Other
ROOM_CATEGORIES = {"6", "7", "12"}
BATH_HINT = "bath"
SUITE_HINT = "suite"

_hotel_categorized_cache = {}


def get_hotel_images_categorized(hotel_code):
    """Returns {room: [...], bath: [...], suite: [...], other: [...]}."""
    if not hotel_code:
        return {"room": [], "bath": [], "suite": [], "other": []}
    if hotel_code in _hotel_categorized_cache:
        return _hotel_categorized_cache[hotel_code]
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
            _hotel_categorized_cache[hotel_code] = {"room": [], "bath": [], "suite": [], "other": []}
            return _hotel_categorized_cache[hotel_code]
        all_images = parse_hotel_images(response.text, limit=300, include_description=True)
    except Exception as exc:
        print(f"Categorized image fetch failed for {hotel_code}: {exc}", flush=True)
        _hotel_categorized_cache[hotel_code] = {"room": [], "bath": [], "suite": [], "other": []}
        return _hotel_categorized_cache[hotel_code]

    buckets = {"room": [], "bath": [], "suite": [], "other": []}
    for img in all_images:
        cat = str(img.get("category") or "").strip()
        desc = (img.get("description") or "").lower()
        if cat == "12" or SUITE_HINT in desc:
            buckets["suite"].append(img["url"])
        elif cat in ROOM_CATEGORIES:
            if BATH_HINT in desc:
                buckets["bath"].append(img["url"])
            else:
                buckets["room"].append(img["url"])
        else:
            buckets["other"].append(img["url"])
    _hotel_categorized_cache[hotel_code] = buckets
    return buckets


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
            print(
                f"Hotel image content failed for {hotel_code}: http_status={response.status_code}, fault={parse_soap_fault(response.text) or 'N/A'}",
                flush=True,
            )
            _hotel_image_cache[hotel_code] = []
        else:
            _hotel_image_cache[hotel_code] = parse_hotel_images(response.text)
    except Exception as exc:
        print(f"Hotel image fetch failed for {hotel_code}: {exc}", flush=True)
        _hotel_image_cache[hotel_code] = []
    return _hotel_image_cache[hotel_code]

def call_hotel_availability(city, checkin, checkout, adults, rooms=1, hotel_code=""):
    require_soap_config()
    print(
        f"SOAP search request: city={city}, hotel_code={hotel_code or '-'}, checkin={checkin}, checkout={checkout}, adults={adults}, rooms={rooms}",
        flush=True,
    )
    envelope = build_start_envelope(AVAILABILITY_ACTION, build_availability_body(city, checkin, checkout, adults, rooms, hotel_code))
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
        dump_path = os.path.join(BASE_DIR, "last_empty_response.xml")
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

def normalize_coordinate(value, kind):
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        number = float(raw)
    except ValueError:
        return raw
    limit = 90 if kind == "lat" else 180
    if -limit <= number <= limit:
        return f"{number:.6f}".rstrip("0").rstrip(".")

    sign = -1 if number < 0 else 1
    compact = abs(number)
    for scale in (100000, 10000, 1000000):
        scaled = sign * (compact / scale)
        if -limit <= scaled <= limit:
            return f"{scaled:.6f}".rstrip("0").rstrip(".")
    return raw

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
        "latitude": normalize_coordinate(position.get("Latitude"), "lat") if position is not None else None,
        "longitude": normalize_coordinate(position.get("Longitude"), "lon") if position is not None else None,
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
    rate_desc = text_of(first_desc(room_stay, "RoomRateDescription")) or text_of(first_desc(room_stay, "RatePlanDescription"))
    room_desc = text_of(first_desc(room_stay, "RoomDescription"))
    description = rate_desc or room_desc
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
        "roomName": room_desc[:120],
        "rateName": rate_desc[:120],
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


def tbo_request(method, endpoint, payload=None):
    if not TBO_USERNAME or not TBO_PASSWORD:
        raise RuntimeError("Set TBO_USERNAME and TBO_PASSWORD in .env before calling TBO APIs.")
    url = f"{TBO_BASE_URL.rstrip('/')}/{endpoint}"
    session = requests.Session()
    session.trust_env = False
    auth = (TBO_USERNAME, TBO_PASSWORD)
    if method == "GET":
        response = session.get(url, auth=auth, timeout=45)
    else:
        response = session.post(url, json=payload or {}, auth=auth, timeout=45)
    response.raise_for_status()
    return response.json()


def amadeus_rest_token():
    import time as _time
    now = _time.time()
    if _amadeus_rest_token["value"] and now < _amadeus_rest_token["expires_at"] - 30:
        return _amadeus_rest_token["value"]
    if not AMADEUS_API_KEY or not AMADEUS_API_SECRET:
        raise RuntimeError("Set AMADEUS_API_KEY and AMADEUS_API_SECRET in .env for Amadeus REST autocomplete.")
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        f"{AMADEUS_REST_BASE.rstrip('/')}/v1/security/oauth2/token",
        data={"grant_type": "client_credentials", "client_id": AMADEUS_API_KEY, "client_secret": AMADEUS_API_SECRET},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    _amadeus_rest_token["value"] = payload.get("access_token")
    _amadeus_rest_token["expires_at"] = now + int(payload.get("expires_in", 1799))
    return _amadeus_rest_token["value"]


def _matches_keyword(value, keyword):
    if not value or not keyword:
        return False
    value_low = value.lower()
    keyword_low = keyword.lower().strip()
    if keyword_low in value_low:
        return True
    tokens = [t for t in keyword_low.split() if t]
    if len(tokens) > 1 and all(t in value_low for t in tokens):
        return True
    return False


def amadeus_rest_cities(keyword, limit=8):
    token = amadeus_rest_token()
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        f"{AMADEUS_REST_BASE.rstrip('/')}/v1/reference-data/locations",
        params={"subType": "CITY", "keyword": keyword, "page[limit]": limit},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if response.status_code >= 400:
        return []
    items = response.json().get("data") or []
    out = []
    for item in items:
        code = item.get("iataCode") or (item.get("address") or {}).get("cityCode") or ""
        name = item.get("name") or ""
        country = (item.get("address") or {}).get("countryName") or item.get("subType") or ""
        if not (_matches_keyword(name, keyword) or _matches_keyword(code, keyword) or _matches_keyword(country, keyword)):
            continue
        if code and name:
            out.append({"code": code, "name": name.title(), "country": country.title() if country else ""})
        if len(out) >= limit:
            break
    return out


_hotels_by_city_cache = {}


def amadeus_rest_hotels_by_city(city_code, hard_limit=300):
    city_code = (city_code or "").upper()
    if not city_code:
        return []
    if city_code in _hotels_by_city_cache:
        return _hotels_by_city_cache[city_code]
    try:
        token = amadeus_rest_token()
    except RuntimeError:
        _hotels_by_city_cache[city_code] = []
        return []
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(
            f"{AMADEUS_REST_BASE.rstrip('/')}/v1/reference-data/locations/hotels/by-city",
            params={"cityCode": city_code},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"Amadeus by-city failed for {city_code}: {exc}", flush=True)
        _hotels_by_city_cache[city_code] = []
        return []
    if response.status_code >= 400:
        _hotels_by_city_cache[city_code] = []
        return []
    items = response.json().get("data") or []
    out = []
    for item in items:
        name = item.get("name") or ""
        hotel_id = item.get("hotelId") or ""
        if name:
            out.append({
                "name": name.title(),
                "hotelId": hotel_id,
                "city": city_code,
                "chainCode": item.get("chainCode") or "",
            })
        if len(out) >= hard_limit:
            break
    _hotels_by_city_cache[city_code] = out
    return out


def amadeus_rest_hotels(city_token_pairs, limit=8):
    matches = []
    for city_code, hotel_tokens in city_token_pairs:
        for hotel in amadeus_rest_hotels_by_city(city_code):
            name_low = hotel["name"].lower()
            if all(token in name_low for token in hotel_tokens):
                matches.append(hotel)
            if len(matches) >= limit:
                return matches
    return matches


def remember_hotel_names(city_code, hotels):
    bucket = _last_hotel_name_index.setdefault(city_code.upper(), [])
    seen = {entry["name"].lower() for entry in bucket}
    for hotel in hotels or []:
        name = (hotel.get("name") or "").strip()
        if name and name.lower() not in seen:
            bucket.append({"name": name, "hotelId": hotel.get("hotelId", "")})
            seen.add(name.lower())
    if len(bucket) > 200:
        del bucket[200:]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/autocomplete")
def autocomplete():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"cities": [], "hotels": [], "source": "empty"})

    amadeus_cities = []
    if AMADEUS_API_KEY and AMADEUS_API_SECRET:
        try:
            amadeus_cities = amadeus_rest_cities(query)
        except Exception as exc:
            print(f"Amadeus city autocomplete failed: {exc}", flush=True)

    tokens = [t for t in query.lower().split() if t]

    local_cities = []
    for entry in IATA_CITY_INDEX:
        haystacks = (entry["name"].lower(), entry["code"].lower(), entry["country"].lower())
        if any(_matches_keyword(h, token) for h in haystacks for token in tokens):
            local_cities.append(entry)

    city_token_pairs = []
    seen_codes = set()
    for entry in amadeus_cities + local_cities:
        code = (entry.get("code") or "").upper()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        haystack = " ".join([entry.get("name", ""), entry.get("country", ""), code]).lower()
        remaining = [t for t in tokens if t not in haystack]
        if not remaining:
            remaining = tokens
        city_token_pairs.append((code, remaining))
        if len(city_token_pairs) >= 3:
            break

    amadeus_hotels = []
    if AMADEUS_API_KEY and AMADEUS_API_SECRET and city_token_pairs:
        try:
            amadeus_hotels = amadeus_rest_hotels(city_token_pairs)
        except Exception as exc:
            print(f"Amadeus hotel autocomplete failed: {exc}", flush=True)

    if len(amadeus_hotels) < 8:
        for city_code, bucket in _hotels_by_city_cache.items():
            if city_code in seen_codes:
                continue
            for hotel in bucket:
                if _matches_keyword(hotel["name"], query):
                    amadeus_hotels.append(hotel)
                if len(amadeus_hotels) >= 8:
                    break
            if len(amadeus_hotels) >= 8:
                break

    local_hotels = []
    for city_code, bucket in _last_hotel_name_index.items():
        for hotel in bucket:
            if _matches_keyword(hotel["name"], query):
                local_hotels.append({
                    "name": hotel["name"],
                    "hotelId": hotel.get("hotelId", ""),
                    "city": city_code,
                })

    cities, seen_city_codes = [], set()
    for entry in amadeus_cities + local_cities:
        code = (entry.get("code") or "").upper()
        if code and code not in seen_city_codes:
            seen_city_codes.add(code)
            cities.append(entry)
        if len(cities) >= 8:
            break

    hotels, seen_hotel_keys = [], set()
    for entry in amadeus_hotels + local_hotels:
        key = (entry.get("hotelId") or entry.get("name") or "").lower()
        if key and key not in seen_hotel_keys:
            seen_hotel_keys.add(key)
            hotels.append(entry)
        if len(hotels) >= 8:
            break

    if amadeus_cities or amadeus_hotels:
        source = "amadeus"
    elif AMADEUS_API_KEY:
        source = "amadeus-empty+local"
    else:
        source = "local"
    return jsonify({"cities": cities, "hotels": hotels, "source": source})


@app.route("/api/search-hotels")
def search_hotels():
    city       = request.args.get("city", "DXB").upper()
    checkin    = request.args.get("checkin")
    checkout   = request.args.get("checkout")
    adults     = request.args.get("adults", 2)
    rooms      = request.args.get("rooms", 1)
    hotel_code = (request.args.get("hotel_code") or "").strip().upper()
    try:
        data, status = call_hotel_availability(city, checkin, checkout, adults, rooms, hotel_code)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"SOAP request failed: {exc}"}), 502
    if status == 200 and isinstance(data, dict):
        remember_hotel_names(city, data.get("hotels", []))
    return jsonify(data), status


@app.route("/api/tbo/countries")
def tbo_countries():
    try:
        return jsonify(tbo_request("GET", "CountryList"))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"TBO request failed: {exc}"}), 502


@app.route("/api/tbo/cities", methods=["POST"])
def tbo_cities():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(tbo_request("POST", "CityList", {"CountryCode": body.get("CountryCode")}))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"TBO request failed: {exc}"}), 502


@app.route("/api/tbo/hotels", methods=["POST"])
def tbo_hotels():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(tbo_request("POST", "TBOHotelCodeList", {"CityCode": body.get("CityCode")}))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"TBO request failed: {exc}"}), 502


@app.route("/api/tbo/hotel-details", methods=["POST"])
def tbo_hotel_details():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(tbo_request("POST", "HotelDetails", {
            "Hotelcodes": str(body.get("Hotelcodes", "")),
            "Language": body.get("Language") or "EN",
        }))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": f"TBO request failed: {exc}"}), 502


_tbo_city_hotels_cache = {}
_tbo_image_cache = {}


def get_tbo_hotel_images(hotel_code):
    """Returns a list of TBO image URLs for the hotel (cached)."""
    code = str(hotel_code or "").strip()
    if not code:
        return []
    if code in _tbo_image_cache:
        return _tbo_image_cache[code]
    try:
        data = tbo_request("POST", "HotelDetails", {"Hotelcodes": code, "Language": "EN"})
    except Exception as exc:
        print(f"TBO image fetch failed for {code}: {exc}", flush=True)
        _tbo_image_cache[code] = []
        return []
    details = (data or {}).get("HotelDetails") or []
    images = []
    seen = set()
    for entry in details:
        if not isinstance(entry, dict):
            continue
        for url in (entry.get("Images") or []):
            if isinstance(url, str) and url.startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                images.append(url)
        single = entry.get("Image")
        if isinstance(single, str) and single.startswith(("http://", "https://")) and single not in seen:
            seen.add(single)
            images.append(single)
    _tbo_image_cache[code] = images
    return images


def tbo_hotels_for_city(city_code):
    city_code = str(city_code or "").strip()
    if not city_code:
        return []
    if city_code in _tbo_city_hotels_cache:
        return _tbo_city_hotels_cache[city_code]
    try:
        data = tbo_request("POST", "TBOHotelCodeList", {"CityCode": city_code})
    except (RuntimeError, requests.RequestException) as exc:
        print(f"TBO TBOHotelCodeList failed for {city_code}: {exc}", flush=True)
        _tbo_city_hotels_cache[city_code] = []
        return []
    out = []
    for h in (data.get("Hotels") or []):
        out.append({
            "name": h.get("HotelName") or "",
            "code": str(h.get("HotelCode") or ""),
            "rating": h.get("HotelRating") or "",
            "address": h.get("Address") or "",
            "city": h.get("CityName") or "",
        })
    _tbo_city_hotels_cache[city_code] = out
    return out


@app.route("/api/tbo/autocomplete-hotels")
def tbo_autocomplete_hotels():
    city_code = (request.args.get("city") or "").strip()
    query = (request.args.get("q") or "").strip().lower()
    if not city_code:
        return jsonify({"hotels": []})
    hotels = tbo_hotels_for_city(city_code)
    if not query:
        return jsonify({"hotels": hotels[:12]})
    out = []
    for h in hotels:
        if query in h["name"].lower():
            out.append(h)
        if len(out) >= 12:
            break
    return jsonify({"hotels": out})


@app.route("/api/tbo/search", methods=["POST"])
def tbo_search():
    body = request.get_json(silent=True) or {}
    checkin = body.get("checkin")
    checkout = body.get("checkout")
    try:
        adults = max(1, int(body.get("adults") or 2))
        rooms = max(1, int(body.get("rooms") or 1))
    except (TypeError, ValueError):
        return jsonify({"error": "adults and rooms must be integers"}), 400
    hotel_codes = (body.get("hotel_codes") or "").strip()
    nationality = (body.get("nationality") or "AE").upper()
    if not checkin or not checkout:
        return jsonify({"error": "checkin and checkout required"}), 400
    if not hotel_codes:
        return jsonify({"error": "hotel_codes required (comma-separated)"}), 400
    pax_rooms = [{"Adults": adults, "Children": 0, "ChildrenAges": []} for _ in range(rooms)]
    payload = {
        "CheckIn": checkin,
        "CheckOut": checkout,
        "HotelCodes": hotel_codes,
        "GuestNationality": nationality,
        "PaxRooms": pax_rooms,
        "ResponseTime": 25,
        "IsDetailedResponse": True,
        "Filters": {"Refundable": False, "NoOfRooms": 0, "MealType": "All"},
    }
    try:
        return jsonify(tbo_request("POST", "Search", payload))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", 502) if hasattr(exc, "response") and exc.response is not None else 502
        body_txt = exc.response.text[:600] if hasattr(exc, "response") and exc.response is not None else str(exc)
        return jsonify({"error": f"TBO Search failed", "status": status, "detail": body_txt}), 502

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


# ====================================================================
# Cross-provider comparison endpoints — driven by hotel_id_mapping.
# ====================================================================

@app.route("/api/mapping/cities")
def mapping_cities():
    from db.mapping_queries import list_mapped_cities
    try:
        return jsonify({"cities": list_mapped_cities()})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/mapping/hotels")
def mapping_hotels():
    from db.mapping_queries import list_mapped_hotels
    city = (request.args.get("city") or "").upper().strip()
    if not city:
        return jsonify({"error": "city (IATA) required"}), 400
    try:
        return jsonify({"city": city, "hotels": list_mapped_hotels(city)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/mapping/search-hotels")
def mapping_search_hotels():
    """Global hotel search across all matched pairs (used by autocomplete)."""
    from db.mapping_queries import search_hotels
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"hotels": []})
    try:
        return jsonify({"hotels": search_hotels(q, limit=25)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/mapping/compare-prices")
def mapping_compare_prices():
    """Fetch live prices from both providers for a matched hotel pair."""
    tbo_id = (request.args.get("tbo_id") or "").strip()
    amadeus_id = (request.args.get("amadeus_id") or "").strip().upper()
    city = (request.args.get("city") or "").upper().strip()
    checkin = request.args.get("checkin")
    checkout = request.args.get("checkout")
    try:
        adults = max(1, int(request.args.get("adults") or 2))
        rooms = max(1, int(request.args.get("rooms") or 1))
    except (TypeError, ValueError):
        return jsonify({"error": "adults and rooms must be integers"}), 400
    nationality = (request.args.get("nationality") or "AE").upper()

    if not (city and checkin and checkout and (tbo_id or amadeus_id)):
        return jsonify({"error": "city, checkin, checkout and at least one hotel id required"}), 400

    result = {"amadeus": None, "tbo": None}

    # Amadeus SOAP availability for this single hotel.
    if amadeus_id:
        try:
            data, status = call_hotel_availability(city, checkin, checkout, adults, rooms, amadeus_id)
            hotels = (data or {}).get("hotels") or []
            top = hotels[0] if hotels else None
            offers = (top or {}).get("offers") or []

            def _ama_price(o):
                try:
                    return float(o.get("totalPrice") or o.get("basePrice") or 9e9)
                except (TypeError, ValueError):
                    return 9e9
            offers_sorted = sorted(offers, key=_ama_price)[:8]
            cheapest = offers_sorted[0] if offers_sorted else {}

            buckets = get_hotel_images_categorized(amadeus_id)

            def pick_images_for_offer(offer, position, gallery_size=6):
                """Choose a thumbnail + gallery (image array) for the given offer."""
                desc = " ".join(
                    str(offer.get(k) or "") for k in ("description", "rateName", "roomName", "roomType")
                ).lower()
                preferred_buckets = []
                if "suite" in desc and buckets["suite"]:
                    preferred_buckets.append("suite")
                if "bath" in desc and buckets["bath"]:
                    preferred_buckets.append("bath")
                preferred_buckets.extend(["room", "suite", "bath", "other"])
                gallery: list[str] = []
                seen: set[str] = set()
                start = position
                for bucket in preferred_buckets:
                    pool = buckets.get(bucket) or []
                    if not pool:
                        continue
                    for j in range(len(pool)):
                        url = pool[(start + j) % len(pool)]
                        if url and url not in seen:
                            seen.add(url)
                            gallery.append(url)
                            if len(gallery) >= gallery_size:
                                break
                    if len(gallery) >= gallery_size:
                        break
                return gallery

            result["amadeus"] = {
                "status": status,
                "hotelId": amadeus_id,
                "name": (top or {}).get("name"),
                "currency": cheapest.get("currency"),
                "cheapestTotal": cheapest.get("totalPrice"),
                "available": bool(top and top.get("available")),
                "offers": [
                    {
                        "roomType": o.get("roomType") or "",
                        "description": o.get("description") or o.get("rateName") or o.get("roomName") or "Room",
                        "bedType": o.get("bedType") or "",
                        "boardType": (o.get("boardType") or "ROOM_ONLY").replace("_", " "),
                        "basePrice": o.get("basePrice"),
                        "totalPrice": o.get("totalPrice"),
                        "avgPerNight": o.get("avgPerNight"),
                        "currency": o.get("currency"),
                        "refundable": o.get("refundable") or "",
                        "cancelDeadline": o.get("cancelDeadline") or "",
                        "images": pick_images_for_offer(o, i),
                    }
                    for i, o in enumerate(offers_sorted)
                ],
            }
        except Exception as exc:
            result["amadeus"] = {"error": str(exc)}

    # TBO Search for this single hotel.
    if tbo_id:
        pax_rooms = [{"Adults": adults, "Children": 0, "ChildrenAges": []} for _ in range(rooms)]
        payload = {
            "CheckIn": checkin,
            "CheckOut": checkout,
            "HotelCodes": tbo_id,
            "GuestNationality": nationality,
            "PaxRooms": pax_rooms,
            "ResponseTime": 25,
            "IsDetailedResponse": True,
            "Filters": {"Refundable": False, "NoOfRooms": 0, "MealType": "All"},
        }
        try:
            data = tbo_request("POST", "Search", payload)
            hotel_results = (data or {}).get("HotelResult") or []
            top = hotel_results[0] if hotel_results else None
            rooms_data = (top or {}).get("Rooms") or []
            def _tbo_price(r):
                try:
                    return float(r.get("TotalFare") or 9e9)
                except (TypeError, ValueError):
                    return 9e9
            rooms_sorted = sorted(rooms_data, key=_tbo_price)[:8]
            cheapest = rooms_sorted[0] if rooms_sorted else {}

            tbo_image_pool = get_tbo_hotel_images(tbo_id)

            def tbo_gallery(position, gallery_size=6):
                if not tbo_image_pool:
                    return []
                n = len(tbo_image_pool)
                seen = set()
                out = []
                for j in range(n):
                    url = tbo_image_pool[(position + j) % n]
                    if url not in seen:
                        seen.add(url)
                        out.append(url)
                        if len(out) >= gallery_size:
                            break
                return out

            result["tbo"] = {
                "status": 200 if top else 204,
                "hotelCode": tbo_id,
                "currency": (top or {}).get("Currency"),
                "cheapestTotal": cheapest.get("TotalFare") if cheapest else None,
                "roomCount": len(rooms_data),
                "available": bool(rooms_data),
                "rooms": [
                    {
                        "name": " · ".join(r.get("Name")) if isinstance(r.get("Name"), list) else (r.get("Name") or "Room"),
                        "mealType": (r.get("MealType") or "").replace("_", " ") or "Room only",
                        "refundable": bool(r.get("IsRefundable")),
                        "inclusion": r.get("Inclusion") or "",
                        "totalFare": r.get("TotalFare"),
                        "totalTax": r.get("TotalTax"),
                        "images": tbo_gallery(i),
                    }
                    for i, r in enumerate(rooms_sorted)
                ],
            }
        except requests.RequestException as exc:
            result["tbo"] = {"error": f"TBO request failed: {exc}"}
        except Exception as exc:
            result["tbo"] = {"error": str(exc)}

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5050, threaded=True)
