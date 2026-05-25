"""Amadeus Enterprise SOAP client — hotel inventory by city.

Uses Hotel_MultiSingleAvailability_10.0 with SummaryOnly=true to enumerate
hotels in a city (production inventory, not the limited test/sandbox set).
Returns hotel_id + name + coords for each hotel that has at least one
available rate in the requested date range.

To approximate the full inventory, call with a generic future date range
(60+ days out, 1-2 nights).
"""
import base64
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SOAP_ACCESS_POINT = os.environ.get("AMADEUS_WEB_SERVICE_ACCESS_POINT", "1ASIWLUXLET")
SOAP_USER_ID = os.environ.get("AMADEUS_USER_ID")
SOAP_PASSWORD = os.environ.get("AMADEUS_CLEAR_PASSWORD") or os.environ.get("BASE64_PWD")
SOAP_OFFICE_ID = os.environ.get("AMADEUS_OFFICE_ID", "DXBAD32AQ")
SOAP_AGENT_DUTY = os.environ.get("AMADEUS_AGENT_DUTY_CODE", "SU")
SOAP_ENDPOINT = os.environ.get(
    "AMADEUS_SOAP_ENDPOINT",
    f"https://nodeD3.production.webservices.amadeus.com/{SOAP_ACCESS_POINT}",
)

AVAILABILITY_ACTION = "http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0"
CONTENT_ACTION = "http://webservices.amadeus.com/OTA_HotelDescriptiveInfoRQ_07.1_1A2007A"


class AmadeusSoapError(RuntimeError):
    pass


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_child(node, name):
    if node is None:
        return None
    for child in list(node):
        if _local_name(child.tag) == name:
            return child
    return None


def _first_desc(node, name):
    if node is None:
        return None
    for child in node.iter():
        if _local_name(child.tag) == name:
            return child
    return None


def _normalise_coord(value, kind: str):
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        number = float(raw)
    except ValueError:
        return None
    limit = 90 if kind == "lat" else 180
    if -limit <= number <= limit:
        return number
    sign = -1 if number < 0 else 1
    compact = abs(number)
    for scale in (100000, 10000, 1000000):
        scaled = sign * (compact / scale)
        if -limit <= scaled <= limit:
            return scaled
    return None


def _password_digest(password: str) -> tuple[str, str, str]:
    nonce = secrets.token_bytes(16)
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S:000Z")
    password_sha1 = hashlib.sha1(password.encode("utf-8")).digest()
    digest = hashlib.sha1(nonce + created.encode("utf-8") + password_sha1).digest()
    return base64.b64encode(digest).decode("ascii"), nonce_b64, created


def _build_envelope(action: str, body_xml: str) -> str:
    if not SOAP_USER_ID or not SOAP_PASSWORD:
        raise AmadeusSoapError(
            "AMADEUS_USER_ID / AMADEUS_CLEAR_PASSWORD missing in .env"
        )
    message_id = str(uuid.uuid4())
    password_digest, nonce_b64, created = _password_digest(SOAP_PASSWORD)
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
        <oas:Username>{escape(SOAP_USER_ID)}</oas:Username>
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


def _build_inventory_body(city_code: str, checkin: str, checkout: str, adults: int = 2, rooms: int = 1) -> str:
    return f"""    <OTA_HotelAvailRQ EchoToken="InventoryScan" Version="4.000" PrimaryLangID="EN"
      SummaryOnly="true" RateRangeOnly="true" ExactMatchOnly="false" SearchCacheLevel="Live"
      RateDetailsInd="false" RequestedCurrency="AED">
      <AvailRequestSegments><AvailRequestSegment InfoSource="Distribution">
        <HotelSearchCriteria AvailableOnlyIndicator="false"><Criterion ExactMatch="true">
          <HotelRef HotelCityCode="{escape(city_code)}"/>
          <StayDateRange Start="{escape(checkin)}" End="{escape(checkout)}"/>
          <RoomStayCandidates><RoomStayCandidate Quantity="{int(rooms)}"><GuestCounts IsPerRoom="true">
            <GuestCount AgeQualifyingCode="10" Count="{int(adults)}"/>
          </GuestCounts></RoomStayCandidate></RoomStayCandidates>
        </Criterion></HotelSearchCriteria>
      </AvailRequestSegment></AvailRequestSegments>
    </OTA_HotelAvailRQ>"""


def _parse_inventory(xml_text: str) -> list[dict]:
    """Return [{hotelId, name, latitude, longitude, chainCode}]"""
    root = ET.fromstring(xml_text)
    fault = _first_desc(root, "Fault")
    if fault is not None:
        fault_str = _first_child(fault, "faultstring")
        raise AmadeusSoapError(
            f"SOAP fault: {(''.join(fault_str.itertext()) if fault_str is not None else '').strip()}"
        )

    hotels: dict[str, dict] = {}
    for node in root.iter():
        if _local_name(node.tag) != "BasicPropertyInfo":
            continue
        hotel_id = node.get("HotelCode") or ""
        if not hotel_id or hotel_id in hotels:
            continue
        position = _first_child(node, "Position")
        lat = _normalise_coord(position.get("Latitude") if position is not None else None, "lat")
        lon = _normalise_coord(position.get("Longitude") if position is not None else None, "lon")
        hotels[hotel_id] = {
            "hotelId": hotel_id,
            "name": node.get("HotelName") or "",
            "latitude": lat,
            "longitude": lon,
            "chainCode": node.get("ChainCode") or "",
        }
    return list(hotels.values())


def _build_content_body(hotel_codes: list[str]) -> str:
    entries = "\n".join(
        f'          <HotelDescriptiveInfo HotelCode="{escape(code)}">'
        '<HotelInfo SendData="true"/><AreaInfo SendRefPoints="true"/><ContactInfo SendData="true"/>'
        '</HotelDescriptiveInfo>'
        for code in hotel_codes
    )
    return f"""    <OTA_HotelDescriptiveInfoRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="CoordsScan" Version="6.001" PrimaryLangID="en">
      <HotelDescriptiveInfos>
{entries}
      </HotelDescriptiveInfos>
    </OTA_HotelDescriptiveInfoRQ>"""


def _parse_descriptive_coords(xml_text: str) -> dict[str, dict]:
    """Return {hotel_code: {latitude, longitude, name}} from DescriptiveInfo response."""
    root = ET.fromstring(xml_text)
    out: dict[str, dict] = {}
    for desc in root.iter():
        if _local_name(desc.tag) != "HotelDescriptiveContent":
            continue
        code = desc.get("HotelCode") or ""
        name = desc.get("HotelName") or ""
        if not code:
            continue
        lat = lon = None
        for node in desc.iter():
            tag = _local_name(node.tag)
            if tag == "Position":
                lat = _normalise_coord(node.get("Latitude"), "lat")
                lon = _normalise_coord(node.get("Longitude"), "lon")
                if lat is not None and lon is not None:
                    break
        out[code] = {"latitude": lat, "longitude": lon, "name": name}
    return out


def hotels_descriptive_info_soap(hotel_codes: list[str], *, batch_size: int = 20, timeout: int = 90) -> dict[str, dict]:
    """Bulk-fetch coords via SOAP OTA_HotelDescriptiveInfoRQ. Returns {hotel_code: {latitude, longitude, name}}."""
    codes = [str(c).strip() for c in hotel_codes if str(c).strip()]
    if not codes:
        return {}
    result: dict[str, dict] = {}
    for start in range(0, len(codes), batch_size):
        chunk = codes[start:start + batch_size]
        envelope = _build_envelope(CONTENT_ACTION, _build_content_body(chunk))
        session = requests.Session()
        session.trust_env = False
        try:
            response = session.post(
                SOAP_ENDPOINT,
                data=envelope.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": CONTENT_ACTION},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            print(f"  DescriptiveInfo batch {start}-{start+len(chunk)} request failed: {exc}")
            continue
        if response.status_code >= 400:
            print(f"  DescriptiveInfo batch HTTP {response.status_code}: {response.text[:300]}")
            continue
        result.update(_parse_descriptive_coords(response.text))
    return result


def hotels_by_city_soap(
    city_code: str,
    *,
    days_ahead: int = 75,
    nights: int = 1,
    adults: int = 2,
    rooms: int = 1,
    timeout: int = 90,
) -> list[dict]:
    """Enumerate hotels in a city via Amadeus production SOAP."""
    code = (city_code or "").upper().strip()
    if not code:
        return []
    checkin = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    checkout = (datetime.utcnow() + timedelta(days=days_ahead + nights)).strftime("%Y-%m-%d")
    envelope = _build_envelope(
        AVAILABILITY_ACTION,
        _build_inventory_body(code, checkin, checkout, adults=adults, rooms=rooms),
    )
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        SOAP_ENDPOINT,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": AVAILABILITY_ACTION},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise AmadeusSoapError(
            f"SOAP HTTP {response.status_code}: {response.text[:500]}"
        )
    return _parse_inventory(response.text)
