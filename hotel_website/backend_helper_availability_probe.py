"""Backend-style Amadeus SOAP operation probe.

This mirrors the production Django helper.py SOAP header style, but runs as a
standalone local test against the Amadeus endpoint from .env.

The bodies are minimal diagnostics. They are designed to check whether each
operation is reachable/provisioned without intentionally creating bookings,
PNRs, cancellations, or reservations.
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

load_dotenv()

AMADEUS_URL = os.environ.get("AMADEUS_URL") or "https://nodeD3.production.webservices.amadeus.com"
AMADEUS_WEB_SERVICE_ACCESS_POINT = os.environ.get("AMADEUS_WEB_SERVICE_ACCESS_POINT") or "1ASIWLUXLET"
AMADEUS_USER_ID = os.environ.get("AMADEUS_USER_ID")
AMADEUS_CLEAR_PASSWORD = os.environ.get("AMADEUS_CLEAR_PASSWORD")
AMADEUS_OFFICE_ID = os.environ.get("AMADEUS_OFFICE_ID") or "DXBAD32AQ"
AMADEUS_DUTY_CODE = os.environ.get("AMADEUS_DUTY_CODE") or os.environ.get("AMADEUS_AGENT_DUTY_CODE") or "SU"
ENDPOINT = os.environ.get("AMADEUS_SOAP_ENDPOINT", f"{AMADEUS_URL.rstrip('/')}/{AMADEUS_WEB_SERVICE_ACCESS_POINT}")

LAST_AVAILABILITY = {
    "hotel_code": "HLTDXB",
    "room_type_code": "",
    "rate_plan_code": "",
    "booking_code": "",
}
SESSION = {"id": "", "sequence": "", "token": ""}


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def password_digest():
    nonce = secrets.token_bytes(32)
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    created = utc_now()
    password_sha1 = hashlib.sha1(AMADEUS_CLEAR_PASSWORD.encode("utf-8")).digest()
    digest = hashlib.sha1(nonce + created.encode("utf-8") + password_sha1).digest()
    return base64.b64encode(digest).decode("ascii"), created, nonce_b64, str(uuid.uuid4())


def build_start_envelope(action, body_xml):
    digest, created, nonce_b64, message_id = password_digest()
    return f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ses="http://xml.amadeus.com/2010/06/Session_v3">
  <soap:Header>
    <ses:Session TransactionStatusCode="Start"/>
    <add:MessageID xmlns:add="http://www.w3.org/2005/08/addressing">{escape(message_id)}</add:MessageID>
    <add:Action xmlns:add="http://www.w3.org/2005/08/addressing">{escape(action)}</add:Action>
    <add:To xmlns:add="http://www.w3.org/2005/08/addressing">{escape(ENDPOINT)}</add:To>
    <link:TransactionFlowLink xmlns:link="http://wsdl.amadeus.com/2010/06/ws/Link_v1"/>
    <oas:Security xmlns:oas="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <oas:UsernameToken xmlns:oas1="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd" oas1:Id="UsernameToken-1">
        <oas:Username>{escape(AMADEUS_USER_ID)}</oas:Username>
        <oas:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</oas:Nonce>
        <oas:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</oas:Password>
        <oas1:Created>{created}</oas1:Created>
      </oas:UsernameToken>
    </oas:Security>
    <AMA_SecurityHostedUser xmlns="http://xml.amadeus.com/2010/06/Security_v1">
      <UserID AgentDutyCode="{escape(AMADEUS_DUTY_CODE)}" POS_Type="1" PseudoCityCode="{escape(AMADEUS_OFFICE_ID)}" RequestorType="U"/>
    </AMA_SecurityHostedUser>
  </soap:Header>
  <soap:Body>
{body_xml}
  </soap:Body>
</soap:Envelope>'''


def build_inseries_envelope(action, body_xml):
    message_id = str(uuid.uuid4())
    try:
        sequence = str(int(SESSION.get("sequence") or "1") + 1)
    except ValueError:
        sequence = SESSION.get("sequence") or "2"
    return f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:ses="http://xml.amadeus.com/2010/06/Session_v3">
  <soap:Header>
    <ses:Session TransactionStatusCode="InSeries">
      <ses:SessionId>{escape(SESSION["id"])}</ses:SessionId>
      <ses:SequenceNumber>{escape(sequence)}</ses:SequenceNumber>
      <ses:SecurityToken>{escape(SESSION["token"])}</ses:SecurityToken>
    </ses:Session>
    <add:MessageID xmlns:add="http://www.w3.org/2005/08/addressing">{escape(message_id)}</add:MessageID>
    <add:Action xmlns:add="http://www.w3.org/2005/08/addressing">{escape(action)}</add:Action>
    <add:To xmlns:add="http://www.w3.org/2005/08/addressing">{escape(ENDPOINT)}</add:To>
    <link:TransactionFlowLink xmlns:link="http://wsdl.amadeus.com/2010/06/ws/Link_v1"/>
  </soap:Header>
  <soap:Body>
{body_xml}
  </soap:Body>
</soap:Envelope>'''


def stay_dates():
    checkin = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    checkout = (datetime.now(timezone.utc).date() + timedelta(days=31)).isoformat()
    return checkin, checkout


def body_hotel_multi_single_availability():
    checkin, checkout = stay_dates()
    return f'''    <OTA_HotelAvailRQ EchoToken="BackendHelperProbe" Version="4.000" PrimaryLangID="EN"
      SummaryOnly="true" RateRangeOnly="true" ExactMatchOnly="false" SearchCacheLevel="Live"
      RateDetailsInd="true" RequestedCurrency="AED">
      <AvailRequestSegments><AvailRequestSegment InfoSource="Distribution">
        <HotelSearchCriteria AvailableOnlyIndicator="true"><Criterion ExactMatch="true">
          <HotelRef HotelCityCode="DXB"/>
          <StayDateRange Start="{checkin}" End="{checkout}"/>
          <RoomStayCandidates><RoomStayCandidate Quantity="1"><GuestCounts IsPerRoom="true">
            <GuestCount AgeQualifyingCode="10" Count="1"/>
          </GuestCounts></RoomStayCandidate></RoomStayCandidates>
        </Criterion></HotelSearchCriteria>
      </AvailRequestSegment></AvailRequestSegments>
    </OTA_HotelAvailRQ>'''


def body_hotel_enhanced_pricing():
    checkin, checkout = stay_dates()
    hotel_code = LAST_AVAILABILITY.get("hotel_code") or "HLTDXB"
    room_type_code = LAST_AVAILABILITY.get("room_type_code") or ""
    rate_plan_code = LAST_AVAILABILITY.get("rate_plan_code") or ""
    booking_code = LAST_AVAILABILITY.get("booking_code") or ""
    rate_plan_xml = f'<RatePlanCandidates><RatePlanCandidate RatePlanCode="{escape(rate_plan_code)}"/></RatePlanCandidates>' if rate_plan_code else ""
    room_type_attr = f' RoomTypeCode="{escape(room_type_code)}"' if room_type_code else ""
    booking_attr = f' BookingCode="{escape(booking_code)}"' if booking_code else ""
    return f'''    <OTA_HotelAvailRQ EchoToken="BackendHelperPricingProbe" Version="4.000" PrimaryLangID="EN"
      SummaryOnly="false" RateRangeOnly="false" AvailRatesOnly="true" RequestedCurrency="AED">
      <AvailRequestSegments><AvailRequestSegment InfoSource="Distribution">
        <HotelSearchCriteria><Criterion ExactMatch="true">
          <HotelRef HotelCode="{escape(hotel_code)}"/>
          <StayDateRange Start="{checkin}" End="{checkout}"/>
          {rate_plan_xml}
          <RoomStayCandidates><RoomStayCandidate{room_type_attr}{booking_attr} Quantity="1">
            <GuestCounts IsPerRoom="true"><GuestCount AgeQualifyingCode="10" Count="1"/></GuestCounts>
          </RoomStayCandidate></RoomStayCandidates>
        </Criterion></HotelSearchCriteria>
      </AvailRequestSegment></AvailRequestSegments>
    </OTA_HotelAvailRQ>'''


def body_hotel_descriptive_info():
    hotel_code = LAST_AVAILABILITY.get("hotel_code") or "HLTDXB"
    return f'''    <OTA_HotelDescriptiveInfoRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="BackendHelperContentProbe" Version="1.008">
      <HotelDescriptiveInfos><HotelDescriptiveInfo HotelCode="{escape(hotel_code)}"/></HotelDescriptiveInfos>
    </OTA_HotelDescriptiveInfoRQ>'''


def body_hotel_complete_reservation_details():
    return '''    <Hotel_CompleteReservationDetails xmlns="http://xml.amadeus.com/HCRDRQ_17_1_1A">
      <retrievalKeyGroup>
        <retrievalKey><reservation><companyId>1A</companyId><controlNumber>ABCDEF</controlNumber><controlType>P</controlType></reservation></retrievalKey>
        <tattooID><referenceDetails><type>S</type><value>1</value></referenceDetails></tattooID>
      </retrievalKeyGroup>
    </Hotel_CompleteReservationDetails>'''


def body_hotel_sell():
    return '''    <Hotel_Sell xmlns="http://xml.amadeus.com/HBKRCQ_20_1_1A">
      <travelAgentRef><status>APE</status><reference><type>OT</type><value>1</value></reference></travelAgentRef>
      <roomStayData><markerRoomStayData/></roomStayData>
    </Hotel_Sell>'''


def body_pnr_add_multi_elements():
    return '''    <PNR_AddMultiElements xmlns="http://xml.amadeus.com/PNRADD_21_1_1A">
      <pnrActions><optionCode>0</optionCode></pnrActions>
    </PNR_AddMultiElements>'''


def body_pnr_retrieve():
    return '''    <PNR_Retrieve xmlns="http://xml.amadeus.com/PNRRET_21_1_1A">
      <retrievalFacts><retrieve><type>2</type></retrieve><reservationOrProfileIdentifier><reservation><controlNumber>ABCDEF</controlNumber></reservation></reservationOrProfileIdentifier></retrievalFacts>
    </PNR_Retrieve>'''


def body_pnr_cancel():
    return '''    <PNR_Cancel xmlns="http://xml.amadeus.com/PNRXCL_21_1_1A">
      <reservationInfo><reservation><controlNumber>ABCDEF</controlNumber></reservation></reservationInfo>
      <pnrActions><optionCode>0</optionCode></pnrActions>
      <cancelElements><entryType>I</entryType><element><identifier>ST</identifier><number>1</number></element></cancelElements>
    </PNR_Cancel>'''


def body_security_signout():
    return '''    <Security_SignOut xmlns="http://xml.amadeus.com/VLSSOQ_04_1_1A"/>'''


PROBES = [
    ("Hotel_MultiSingleAvailability_10.0", "http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0", body_hotel_multi_single_availability),
    ("Hotel_EnhancedPricing_2.0", "http://webservices.amadeus.com/Hotel_EnhancedPricing_2.0", body_hotel_enhanced_pricing),
    ("Hotel_DescriptiveInfo", "http://webservices.amadeus.com/OTA_HotelDescriptiveInfoRQ_07.1_1A2007A", body_hotel_descriptive_info),
    ("Hotel_CompleteReservationDetails", "http://webservices.amadeus.com/HCRDRQ_17_1_1A", body_hotel_complete_reservation_details),
    ("Hotel_Sell", "http://webservices.amadeus.com/HBKRCQ_20_1_1A", body_hotel_sell),
    ("PNR_AddMultiElements", "http://webservices.amadeus.com/PNRADD_21_1_1A", body_pnr_add_multi_elements),
    ("PNR_Retrieve", "http://webservices.amadeus.com/PNRRET_21_1_1A", body_pnr_retrieve),
    ("PNR_Cancel", "http://webservices.amadeus.com/PNRXCL_21_1_1A", body_pnr_cancel),
    ("Security_SignOut", "http://webservices.amadeus.com/VLSSOQ_04_1_1A", body_security_signout),
]


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def remember_response_context(root):
    for node in root.iter():
        if local_name(node.tag) == "Session":
            for child in node:
                child_name = local_name(child.tag)
                value = "".join(child.itertext()).strip()
                if child_name == "SessionId":
                    SESSION["id"] = value
                elif child_name == "SequenceNumber":
                    SESSION["sequence"] = value
                elif child_name == "SecurityToken":
                    SESSION["token"] = value
    for node in root.iter():
        if local_name(node.tag) == "BasicPropertyInfo" and node.get("HotelCode"):
            LAST_AVAILABILITY["hotel_code"] = node.get("HotelCode")
            break
    for node in root.iter():
        if local_name(node.tag) == "RoomRate" and node.get("BookingCode"):
            LAST_AVAILABILITY["booking_code"] = node.get("BookingCode", "")
            LAST_AVAILABILITY["room_type_code"] = node.get("RoomTypeCode", "")
            LAST_AVAILABILITY["rate_plan_code"] = node.get("RatePlanCode", "")
            break


def classify_response(http_status, body_text):
    if http_status >= 400 and not body_text.strip().startswith("<"):
        return "HTTP_ERROR", f"http {http_status}"
    try:
        root = ET.fromstring(body_text)
    except ET.ParseError as exc:
        return "PARSE_ERROR", str(exc)

    remember_response_context(root)

    for node in root.iter():
        if local_name(node.tag) == "Fault":
            return "SOAP_FAULT", " ".join("".join(node.itertext()).split())[:300]

    errors = []
    warnings = []
    hotels = 0
    for node in root.iter():
        name = local_name(node.tag)
        if name == "Error":
            text = " ".join("".join(node.itertext()).split())
            attrs = " ".join(f"{k}={v}" for k, v in node.attrib.items())
            errors.append(text or attrs)
        elif name == "Warning":
            text = " ".join("".join(node.itertext()).split())
            attrs = " ".join(f"{k}={v}" for k, v in node.attrib.items())
            warnings.append(text or attrs)
        elif name == "BasicPropertyInfo":
            hotels += 1

    if hotels:
        return "SUCCESS", f"received {hotels} hotel property nodes; sample={LAST_AVAILABILITY}; session={'yes' if SESSION.get('id') else 'no'}"
    if errors:
        first = errors[0]
        if "Status=1A" in first and "Code" not in first:
            return "NOT_PROVISIONED_OR_IP_BLOCKED", first
        return "PROVISIONED_OR_AMADEUS_ERROR", first[:300]
    if warnings:
        return "PROVISIONED_OR_AMADEUS_WARNING", warnings[0][:300]
    return "SUCCESS_EMPTY", "valid XML response with no hotel nodes or errors"


def probe(name, action, body_fn):
    if name == "Hotel_EnhancedPricing_2.0" and SESSION.get("id") and SESSION.get("token"):
        envelope = build_inseries_envelope(action, body_fn())
    else:
        envelope = build_start_envelope(action, body_fn())
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(
            ENDPOINT,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": action},
            timeout=45,
        )
    except requests.RequestException as exc:
        return name, "REQUEST_ERROR", str(exc)
    status, detail = classify_response(response.status_code, response.text)
    return name, f"HTTP {response.status_code} {status}", detail


def main():
    if not AMADEUS_USER_ID or not AMADEUS_CLEAR_PASSWORD:
        print("ERROR: AMADEUS_USER_ID and AMADEUS_CLEAR_PASSWORD must exist in .env")
        return 1
    print(f"Endpoint: {ENDPOINT}")
    print(f"User: {AMADEUS_USER_ID} | Office: {AMADEUS_OFFICE_ID} | Duty: {AMADEUS_DUTY_CODE}")
    print(f"Probing {len(PROBES)} backend-style operations")
    results = []
    for name, action, body_fn in PROBES:
        print(f"\n--- {name}")
        print(f"SOAPAction: {action}")
        result = probe(name, action, body_fn)
        results.append(result)
        print(result[1])
        print(f"Detail: {result[2]}")
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"{'TRANSACTION':<42} {'STATUS':<42} DETAIL")
    print("-" * 110)
    for name, status, detail in results:
        print(f"{name:<42} {status:<42} {detail[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

