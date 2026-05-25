"""Dump raw SOAP OTA_HotelDescriptiveInfoRQ response to inspect GuestRoom structure."""
import sys
import requests

from db.amadeus_soap import _build_envelope, CONTENT_ACTION, SOAP_ENDPOINT
from xml.sax.saxutils import escape


def _build_content_body(hotel_code: str) -> str:
    return f"""    <OTA_HotelDescriptiveInfoRQ xmlns="http://www.opentravel.org/OTA/2003/05" EchoToken="Dump" Version="6.001" PrimaryLangID="en">
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


def main(code: str) -> None:
    envelope = _build_envelope(CONTENT_ACTION, _build_content_body(code))
    session = requests.Session()
    session.trust_env = False
    response = session.post(
        SOAP_ENDPOINT,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": CONTENT_ACTION},
        timeout=90,
    )
    path = f"content_dump_{code}.xml"
    with open(path, "w", encoding="utf-8") as f:
        f.write(response.text)
    text = response.text
    print(f"status {response.status_code}, {len(text)} bytes -> {path}")
    print()
    for needle in ("GuestRoom", "FacilityInfo", "MultimediaObject", "ImageItem", "Description", "RoomType", "RoomTypeCode"):
        print(f"  {needle:<20} count={text.count(needle)}")


if __name__ == "__main__":
    main((sys.argv[1] if len(sys.argv) > 1 else "HLFJR705"))
