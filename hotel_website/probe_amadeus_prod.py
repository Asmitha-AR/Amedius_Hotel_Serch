"""
Probe each Amadeus SOAP transaction defined in Itravelle_PRD_1.1 against the
production endpoint. Goal: find out which WSAP operations are provisioned for
this account.

Each probe sends the smallest envelope the transaction's schema allows. The
response is then classified:

  PROVISIONED   - Amadeus parsed the body and returned a specific error
                  (missing field, invalid value, etc.). The transaction is
                  reachable on this account.
  NOT_PROVISIONED - Amadeus returned the generic <Error Status="1A"/> with no
                  code. Typical pattern when the WSAP isn't authorised for the
                  transaction OR the public IP isn't whitelisted for prod.
  SOAP_FAULT    - Server-side fault (auth, policy, framework).
  HTTP_ERROR    - Non-2xx HTTP response.
  SUCCESS       - Transaction returned a valid (non-error) reply.

NOTE: All probes use minimal bodies. They will not create bookings, PNRs, or
other persistent state.
"""

import os
import uuid
import base64
import hashlib
import secrets
import sys
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import requests
from dotenv import load_dotenv

load_dotenv()

USER_ID    = os.environ.get("AMADEUS_USER_ID")
PASSWORD   = os.environ.get("AMADEUS_CLEAR_PASSWORD")
OFFICE_ID  = os.environ.get("AMADEUS_OFFICE_ID", "DXBAD32AQ")
DUTY_CODE  = os.environ.get("AMADEUS_AGENT_DUTY_CODE", "SU")
ENDPOINT   = os.environ.get(
    "AMADEUS_SOAP_ENDPOINT",
    "https://nodeD3.production.webservices.amadeus.com/1ASIWLUXLET",
)

if not USER_ID or not PASSWORD:
    print("ERROR: AMADEUS_USER_ID and AMADEUS_CLEAR_PASSWORD must be set in .env")
    sys.exit(1)


def password_digest(password):
    nonce = secrets.token_bytes(16)
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S:000Z")
    pw_sha1 = hashlib.sha1(password.encode("utf-8")).digest()
    digest = hashlib.sha1(nonce + created.encode("utf-8") + pw_sha1).digest()
    return base64.b64encode(digest).decode("ascii"), nonce_b64, created


def build_envelope(action, body_xml):
    msg_id = f"urn:uuid:{uuid.uuid4()}"
    echo = str(uuid.uuid4())
    digest, nonce_b64, created = password_digest(PASSWORD)
    user_id = escape(USER_ID)
    office_id = escape(OFFICE_ID)
    duty = escape(DUTY_CODE)
    endpoint = escape(ENDPOINT)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
  xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:awsse="http://xml.amadeus.com/2010/06/Session_v3"
  xmlns:awsl="http://wsdl.amadeus.com/2010/06/ws/Link_v1"
  xmlns:amasec="http://xml.amadeus.com/2010/06/Security_v1"
  xmlns:wsa="http://www.w3.org/2005/08/addressing"
  xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
  xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
  <soapenv:Header>
    <wsa:MessageID>{msg_id}</wsa:MessageID>
    <wsa:Action>{escape(action)}</wsa:Action>
    <wsa:To>{endpoint}</wsa:To>
    <awsse:Session TransactionStatusCode="Start"/>
    <awsl:TransactionFlowLink>
      <awsl:Consumer>
        <awsl:UniqueID>{echo}</awsl:UniqueID>
      </awsl:Consumer>
    </awsl:TransactionFlowLink>
    <amasec:AMA_SecurityHostedUser>
      <amasec:UserID AgentDutyCode="{duty}" POS_Type="1" PseudoCityCode="{office_id}" RequestorType="U"/>
    </amasec:AMA_SecurityHostedUser>
    <wsse:Security>
      <wsse:UsernameToken>
        <wsse:Username>{user_id}</wsse:Username>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce_b64}</wsse:Nonce>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
{body_xml}
  </soapenv:Body>
</soapenv:Envelope>"""


# Minimal probe bodies for each transaction. Each is just the root element with
# the right namespace. Amadeus will either accept and complain about missing
# required content (= provisioned) or reject with empty Status="1A" (= not
# provisioned / IP-blocked).

def body_ota_hotel_avail():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""    <OTA_HotelAvailRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="probe" TimeStamp="{now}" Version="4.000">
      <POS><Source><RequestorID ID="{escape(USER_ID)}" Type="5"/><BookingChannel Type="7"/></Source></POS>
      <AvailRequestSegments>
        <AvailRequestSegment>
          <HotelSearchCriteria>
            <Criterion><HotelRef HotelCityCode="DXB" HotelCodeContext="1A"/></Criterion>
          </HotelSearchCriteria>
        </AvailRequestSegment>
      </AvailRequestSegments>
    </OTA_HotelAvailRQ>"""


def body_ota_hotel_descriptive_info():
    return """    <OTA_HotelDescriptiveInfoRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="probe" Version="1.008">
      <HotelDescriptiveInfos>
        <HotelDescriptiveInfo HotelCode="HLTDXB"/>
      </HotelDescriptiveInfos>
    </OTA_HotelDescriptiveInfoRQ>"""


def body_ota_notif_report():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""    <OTA_NotifReportRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="probe" TimeStamp="{now}" Version="2.001">
      <Success/>
    </OTA_NotifReportRQ>"""


def body_hotel_complete_reservation_details():
    return """    <Hotel_CompleteReservationDetails xmlns="http://xml.amadeus.com/HCRDRQ_17_1_1A">
      <retrievalKeyGroup>
        <retrievalKey>
          <reservation>
            <companyId>1A</companyId>
            <controlNumber>ABCDEF</controlNumber>
            <controlType>P</controlType>
          </reservation>
        </retrievalKey>
      </retrievalKeyGroup>
    </Hotel_CompleteReservationDetails>"""


def body_hotel_sell():
    return """    <Hotel_Sell xmlns="http://xml.amadeus.com/HBKRCQ_20_1_1A">
      <roomStayData>
        <markerRoomStayData/>
      </roomStayData>
    </Hotel_Sell>"""


def body_pnr_add_multi_elements():
    return """    <PNR_AddMultiElements xmlns="http://xml.amadeus.com/PNRADD_21_1_1A">
      <pnrActions>
        <optionCode>0</optionCode>
      </pnrActions>
    </PNR_AddMultiElements>"""


def body_pnr_cancel():
    return """    <PNR_Cancel xmlns="http://xml.amadeus.com/PNRXCL_21_1_1A">
      <pnrActions>
        <optionCode>0</optionCode>
      </pnrActions>
    </PNR_Cancel>"""


def body_pnr_retrieve():
    return """    <PNR_Retrieve xmlns="http://xml.amadeus.com/PNRRET_21_1_1A">
      <retrievalFacts>
        <retrieve>
          <type>2</type>
        </retrieve>
        <reservationOrProfileIdentifier>
          <reservation>
            <controlNumber>ABCDEF</controlNumber>
          </reservation>
        </reservationOrProfileIdentifier>
      </retrievalFacts>
    </PNR_Retrieve>"""


def body_security_signout():
    return """    <Security_SignOut xmlns="http://xml.amadeus.com/VLSSOQ_04_1_1A">
      <SessionId>probe</SessionId>
    </Security_SignOut>"""


PROBES = [
    ("Hotel_MultiSingleAvailability_10.0", "http://webservices.amadeus.com/Hotel_MultiSingleAvailability_10.0", body_ota_hotel_avail),
    ("Hotel_MultiAvailability_10.0",       "http://webservices.amadeus.com/Hotel_MultiAvailability_10.0",       body_ota_hotel_avail),
    ("Hotel_EnhancedSingleAvail_2.0",      "http://webservices.amadeus.com/Hotel_EnhancedSingleAvail_2.0",      body_ota_hotel_avail),
    ("Hotel_EnhancedPricing_2.0",          "http://webservices.amadeus.com/Hotel_EnhancedPricing_2.0",          body_ota_hotel_avail),
    ("Hotel_DescriptiveInfo",              "http://webservices.amadeus.com/OTA_HotelDescriptiveInfoRQ_07.1_1A2007A", body_ota_hotel_descriptive_info),
    ("Hotel_ContentNotifReport_1.0",       "http://webservices.amadeus.com/Hotel_ContentNotifReport_1.0",       body_ota_notif_report),
    ("Hotel_CompleteReservationDetails",   "http://webservices.amadeus.com/HCRDRQ_17_1_1A",                     body_hotel_complete_reservation_details),
    ("Hotel_Sell",                         "http://webservices.amadeus.com/HBKRCQ_20_1_1A",                     body_hotel_sell),
    ("PNR_AddMultiElements",               "http://webservices.amadeus.com/PNRADD_21_1_1A",                     body_pnr_add_multi_elements),
    ("PNR_Retrieve",                       "http://webservices.amadeus.com/PNRRET_21_1_1A",                     body_pnr_retrieve),
    ("PNR_Cancel",                         "http://webservices.amadeus.com/PNRXCL_21_1_1A",                     body_pnr_cancel),
    ("Security_SignOut",                   "http://webservices.amadeus.com/VLSSOQ_04_1_1A",                     body_security_signout),
]


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def classify(http_status, body_text):
    if http_status >= 400 and not body_text.strip().startswith("<"):
        return "HTTP_ERROR", f"http {http_status}", ""
    try:
        root = ET.fromstring(body_text)
    except ET.ParseError as exc:
        return "PARSE_ERROR", str(exc), body_text[:200]

    fault = None
    for node in root.iter():
        if local_name(node.tag) == "Fault":
            fault = node
            break
    if fault is not None:
        fault_text = "".join(fault.itertext()).strip()
        return "SOAP_FAULT", fault_text[:200], ""

    errors = []
    for node in root.iter():
        if local_name(node.tag) in ("Error", "Warning"):
            text = "".join(node.itertext()).strip()
            attrs = " ".join(f"{k}={v}" for k, v in node.attrib.items())
            errors.append((text, attrs))

    if not errors:
        return "SUCCESS", "no errors", ""

    # Look at the first error to classify
    text, attrs = errors[0]
    if not text and ("Status=1A" in attrs or "Status=\"1A\"" in attrs) and "Code" not in attrs:
        # Empty Error element with only Status="1A" -> account-level rejection
        return "NOT_PROVISIONED", f"empty Status=1A error ({attrs})", ""
    detail = text or attrs
    return "PROVISIONED", detail[:200], ""


def probe(name, action, body_fn):
    print(f"\n--- {name}")
    print(f"    SOAPAction: {action}")
    envelope = build_envelope(action, body_fn())
    session = requests.Session()
    session.trust_env = False
    try:
        resp = session.post(
            ENDPOINT,
            data=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": action,
            },
            timeout=45,
        )
    except requests.RequestException as exc:
        print(f"    REQUEST_ERROR: {exc}")
        return name, "REQUEST_ERROR", str(exc)

    status, detail, _ = classify(resp.status_code, resp.text)
    print(f"    HTTP {resp.status_code} -> {status}")
    print(f"    detail: {detail}")
    return name, status, detail


def main():
    print(f"Endpoint: {ENDPOINT}")
    print(f"User: {USER_ID} | Office: {OFFICE_ID} | Duty: {DUTY_CODE}")
    print(f"Probing {len(PROBES)} operations from Itravelle_PRD_1.1 WSDLs...\n")
    results = []
    for name, action, body_fn in PROBES:
        results.append(probe(name, action, body_fn))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'TRANSACTION':<45} {'STATUS':<18} DETAIL")
    print("-" * 90)
    for name, status, detail in results:
        print(f"{name:<45} {status:<18} {detail[:50]}")


if __name__ == "__main__":
    main()
