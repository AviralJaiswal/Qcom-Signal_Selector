import logging
import re
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.address import Address

logger = logging.getLogger(__name__)

NOMINATIM_USER_AGENT = "SignalSelectorTelecomApp/1.0 (contact: dev@prodapt.com)"


def clean_street_address(text: str, pincode: str | None = None) -> str:
    """Clean natural language conversational phrases and pincodes from address text."""
    if not text:
        return ""
    cleaned = text.strip()

    # 1. Remove 6-digit pincodes from the street address text
    cleaned = re.sub(r"\b[1-9][0-9]{5}\b", "", cleaned).strip()
    if pincode and pincode.strip() in cleaned:
        cleaned = cleaned.replace(pincode.strip(), "").strip()

    # 2. Strip conversational words/phrases anywhere in input
    conv_words = r"\b(?:okay|ok|yes|yeah|yep|sure|hi|hello|hey|my|your|here|is|this|address|add|location|pincode|pin\s+code|zip\s+code|postal\s+code|check|serviceability|coverage|live|at|located)\b"
    cleaned = re.sub(conv_words, "", cleaned, flags=re.IGNORECASE).strip()

    # 3. Clean leading/trailing punctuation and extra whitespace
    cleaned = re.sub(r"^[,\s:-]+|[,\s:-]+$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If remaining text is too short or empty, return empty string
    if len(cleaned) < 3 or cleaned.lower() in {"india", "area"}:
        return ""

    return cleaned



METRO_TELECOM_MAP = [
    (("delhi", "gurgaon", "gurugram", "noida", "ghaziabad", "faridabad", "ncr"), ("110", "122", "201"), "Delhi NCR"),
    (("mumbai", "navi mumbai", "thane", "pune", "kalyan"), ("400", "401", "402", "403", "404", "411"), "Mumbai"),
    (("bengaluru", "bangalore"), ("560", "561", "562"), "Bengaluru"),
    (("hyderabad", "secunderabad"), ("500", "501", "502"), "Hyderabad"),
    (("chennai",), ("600",), "Chennai"),
    (("kolkata", "calcutta", "howrah"), ("700", "711"), "Kolkata"),
]

STATE_TELECOM_MAP = [
    (("maharashtra", "goa"), "Maharashtra & Goa"),
    (("gujarat", "ahmedabad", "surat", "vadodara", "rajkot"), "Gujarat"),
    (("andhra", "telangana", "visakhapatnam", "vijayawada", "tirupati", "warangal"), "Andhra Pradesh & Telangana"),
    (("karnataka", "mysore", "mangalore", "hubli", "belgaum"), "Karnataka"),
    (("tamil nadu", "coimbatore", "madurai", "trichy", "salem", "tirupur"), "Tamil Nadu"),
    (("kerala", "kochi", "trivandrum", "thiruvananthapuram", "kozhikode", "thrissur"), "Kerala"),
    (("punjab", "haryana", "chandigarh", "amritsar", "ludhiana", "jalandhar", "panchkula"), "Punjab & Haryana"),
    (("up east", "lucknow", "kanpur", "varanasi", "allahabad", "prayagraj", "gorakhpur", "ayodhya"), "UP East"),
    (("up west", "uttar pradesh", "meerut", "agra", "bareilly", "aligarh", "mathura"), "UP West"),
    (("rajasthan", "jaipur", "udaipur", "jodhpur", "kota", "bikaner"), "Rajasthan"),
    (("west bengal", "sikkim", "siliguri", "gangtok", "darjeeling"), "West Bengal & Sikkim"),
    (("bihar", "jharkhand", "patna", "ranchi", "gaya", "jamshedpur", "dhanbad"), "Bihar & Jharkhand"),
    (("odisha", "orissa", "bhubaneswar", "cuttack", "puri", "rourkela"), "Odisha"),
    (("assam", "meghalaya", "manipur", "nagaland", "tripura", "mizoram", "arunachal", "guwahati", "shillong", "imphal"), "North East & Assam"),
    (("madhya pradesh", "chhattisgarh", "bhopal", "indore", "raipur", "gwalior", "jabalpur"), "MP & Chhattisgarh"),
]

PINCODE_PREFIX_MAP = [
    (("11", "12", "13", "14", "15", "16"), "Punjab & Haryana"),
    (("17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28"), "UP West"),
    (("30", "31", "32", "33", "34"), "Rajasthan"),
    (("36", "37", "38", "39"), "Gujarat"),
    (("40", "41", "42", "43", "44"), "Maharashtra & Goa"),
    (("45", "46", "47", "48", "49"), "MP & Chhattisgarh"),
    (("50", "51", "52", "53"), "Andhra Pradesh & Telangana"),
    (("56", "57", "58", "59"), "Karnataka"),
    (("60", "61", "62", "63", "64"), "Tamil Nadu"),
    (("67", "68", "69"), "Kerala"),
    (("70", "71", "72", "73", "74"), "West Bengal & Sikkim"),
    (("75", "76", "77"), "Odisha"),
    (("78", "79"), "North East & Assam"),
    (("80", "81", "82", "83", "84", "85"), "Bihar & Jharkhand"),
]


def get_telecom_circle(state: str = "", city: str = "", display_name: str = "", pincode: str = "") -> str:
    """Map detected Indian state, city, display_name, or pincode to exact Telecom Circle key using structured map tables."""
    loc_str = f"{city} {state} {display_name}".lower()
    pin = (pincode or "").strip()

    # 1. Metro Circles (Higher Priority)
    for keywords, pin_prefixes, circle in METRO_TELECOM_MAP:
        if any(k in loc_str for k in keywords) or pin.startswith(pin_prefixes):
            return circle

    # 2. Zonal/State Telecom Circles
    for keywords, circle in STATE_TELECOM_MAP:
        if any(k in loc_str for k in keywords):
            return circle

    # 3. Pincode Prefix Fallbacks
    for pin_prefixes, circle in PINCODE_PREFIX_MAP:
        if pin.startswith(pin_prefixes):
            return circle

    return "Delhi NCR"


def get_region_from_state(state: str, city: str = "", display_name: str = "", pincode: str = "") -> str:
    return get_telecom_circle(state=state, city=city, display_name=display_name, pincode=pincode)


def _olamaps_pincode_lookup(pincode: str) -> dict | None:
    """Geocode pincode using OLA Maps API as primary provider."""
    from app.config import get_settings
    from app.services.http_client import requests_verify_setting
    settings = get_settings()
    api_key = settings.olamaps_api_key
    if not api_key:
        logger.warning("OLAMAPS_API_KEY is not configured in .env")
        return None
    url = f"https://api.olamaps.io/places/v1/geocode?address={pincode}&api_key={api_key}"
    headers = {"X-Request-Id": f"sig-sel-pin-{pincode}", "User-Agent": NOMINATIM_USER_AGENT}
    for verify_ssl in (requests_verify_setting(), False):
        try:
            res = requests.get(url, headers=headers, timeout=4, verify=verify_ssl)
            if res.status_code == 200:
                data = res.json()
                results = data.get("geocodingResults") or data.get("results") or []
                if results:
                    item = results[0]
                    formatted = item.get("formatted_address", "")
                    loc = item.get("geometry", {}).get("location", {})
                    
                    city = "Metro Center"
                    state = "India"
                    for comp in item.get("address_components", []):
                        types = comp.get("types", [])
                        if "locality" in types or "administrative_area_level_2" in types:
                            city = comp.get("short_name") or comp.get("long_name") or city
                        if "administrative_area_level_1" in types:
                            state = comp.get("short_name") or comp.get("long_name") or state
                            
                    region = get_telecom_circle(state=state, city=city, display_name=formatted, pincode=pincode)
                    logger.info("OLA Maps pincode lookup successful for %s: city=%s, state=%s", pincode, city, state)
                    return {
                        "found": True,
                        "serviceable": True,
                        "provider": "OLAMAPS",
                        "pincode": pincode,
                        "city": city,
                        "state": state,
                        "region": region,
                        "lat": loc.get("lat"),
                        "lon": loc.get("lng"),
                        "display_name": formatted or f"{city}, {state}, {pincode}",
                    }
        except Exception as exc:
            logger.warning("OLA Maps pincode lookup attempt (verify=%s) failed for %s: %s", verify_ssl, pincode, exc)
    return None


def _extract_postal_code(components: list[dict]) -> str | None:
    for comp in components or []:
        if "postal_code" in (comp.get("types") or []):
            return (comp.get("short_name") or comp.get("long_name") or "").strip()
    return None


def _olamaps_address_lookup(street_address: str, pincode: str) -> dict | None:
    """Geocode full street address using OLA Maps API as primary provider."""
    from app.config import get_settings
    from app.services.http_client import requests_verify_setting
    settings = get_settings()
    api_key = settings.olamaps_api_key
    if not api_key:
        logger.warning("OLAMAPS_API_KEY is not configured in .env")
        return None
    query = f"{street_address}, {pincode}, India"
    url = f"https://api.olamaps.io/places/v1/geocode?address={requests.utils.quote(query)}&api_key={api_key}"
    headers = {"X-Request-Id": f"sig-sel-addr-{pincode}", "User-Agent": NOMINATIM_USER_AGENT}
    for verify_ssl in (requests_verify_setting(), False):
        try:
            res = requests.get(url, headers=headers, timeout=4, verify=verify_ssl)
            if res.status_code == 200:
                data = res.json()
                results = data.get("geocodingResults") or data.get("results") or []
                if results:
                    item = results[0]
                    formatted = item.get("formatted_address", "")
                    loc = item.get("geometry", {}).get("location", {})
                    components = item.get("address_components", [])

                    returned_pin = _extract_postal_code(components)
                    if returned_pin and returned_pin.strip() != pincode.strip():
                        input_zone = pincode.strip()[:2]
                        ret_zone = returned_pin.strip()[:2]
                        if input_zone != ret_zone:
                            logger.warning(
                                "OLA Maps address/pincode mismatch: input=%s returned=%s for '%s' - rejecting as not legit",
                                pincode, returned_pin, street_address,
                            )
                            return None

                    city = "Metro Center"
                    state = "India"
                    for comp in components:
                        types = comp.get("types", [])
                        if "locality" in types or "administrative_area_level_2" in types:
                            city = comp.get("short_name") or comp.get("long_name") or city
                        if "administrative_area_level_1" in types:
                            state = comp.get("short_name") or comp.get("long_name") or state

                    region = get_telecom_circle(state=state, city=city, display_name=formatted, pincode=pincode)

                    # Prefer OLA Maps returned formatted address directly for exact plot/locality precision
                    if formatted and len(formatted.strip()) > 10:
                        if returned_pin and returned_pin.strip() != pincode.strip() and returned_pin.strip() in formatted:
                            formatted = formatted.replace(returned_pin.strip(), pincode.strip())
                    else:
                        clean_street = street_address.strip().title() if street_address else ""
                        formatted = f"{clean_street}, {city}, {state} {pincode.strip()}, India"

                    logger.info("OLA Maps address lookup successful for %s, %s: city=%s, state=%s", street_address, pincode, city, state)
                    return {
                        "found": True,
                        "serviceable": True,
                        "address_qualified": True,
                        "provider": "OLAMAPS",
                        "pincode": pincode,
                        "street_address": street_address,
                        "formatted_address": formatted,
                        "city": city,
                        "state": state,
                        "region": region,
                        "lat": loc.get("lat"),
                        "lon": loc.get("lng"),
                    }
        except Exception as exc:
            logger.warning("OLA Maps address lookup attempt (verify=%s) failed for %s, %s: %s", verify_ssl, street_address, pincode, exc)
    return None


def _nominatim_pincode_lookup(pincode: str) -> dict | None:
    """Geocode pincode using Nominatim (OpenStreetMap) API fallback with custom User-Agent."""
    url = f"https://nominatim.openstreetmap.org/search?postalcode={pincode}&country=India&format=json&addressdetails=1"
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    try:
        res = requests.get(url, headers=headers, timeout=2)
        if res.status_code == 200 and res.json():
            item = res.json()[0]
            addr = item.get("address", {})
            city = addr.get("city") or addr.get("state_district") or addr.get("county") or addr.get("town") or addr.get("suburb") or "Metro Center"
            state = addr.get("state") or "India"
            display_name = item.get("display_name", "")
            region = get_telecom_circle(state=state, city=city, display_name=display_name, pincode=pincode)
            return {
                "found": True,
                "serviceable": True,
                "provider": "NOMINATIM",
                "pincode": pincode,
                "city": city,
                "state": state,
                "region": region,
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "display_name": display_name,
            }
    except Exception as exc:
        logger.warning("Nominatim pincode lookup failed for %s: %s", pincode, exc)
    return None


def _nominatim_address_lookup(street_address: str, pincode: str) -> dict | None:
    """Geocode full street address using Nominatim (OpenStreetMap) API fallback with custom User-Agent."""
    query = f"{street_address}, {pincode}, India"
    url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(query)}&format=json&addressdetails=1"
    headers = {"User-Agent": NOMINATIM_USER_AGENT}
    try:
        res = requests.get(url, headers=headers, timeout=3)
        items = res.json() if res.status_code == 200 and res.json() else []
        if not items:
            # Fallback to postalcode query if specific street building is not indexed in OSM
            url2 = f"https://nominatim.openstreetmap.org/search?postalcode={pincode}&country=India&format=json&addressdetails=1"
            res2 = requests.get(url2, headers=headers, timeout=3)
            items = res2.json() if res2.status_code == 200 and res2.json() else []

        if items:
            item = items[0]
            addr = item.get("address", {})
            returned_pin = (addr.get("postcode") or "").strip()
            if returned_pin and returned_pin != pincode.strip():
                input_zone = pincode.strip()[:2]
                ret_zone = returned_pin[:2]
                if input_zone != ret_zone:
                    logger.warning(
                        "Nominatim address/pincode mismatch: input=%s returned=%s for '%s' - rejecting as not legit",
                        pincode, returned_pin, street_address,
                    )
                    return None
            city = addr.get("city") or addr.get("state_district") or addr.get("county") or addr.get("town") or addr.get("suburb") or "Metro Center"
            state = addr.get("state") or "India"
            display_name = item.get("display_name", "")
            region = get_telecom_circle(state=state, city=city, display_name=display_name, pincode=pincode)

            clean_street = street_address.strip().title() if street_address else ""
            if clean_street and clean_street.lower() not in display_name.lower():
                formatted = f"{clean_street}, {city}, {state} {pincode.strip()}, India"
            else:
                formatted = display_name

            return {
                "found": True,
                "serviceable": True,
                "address_qualified": True,
                "provider": "NOMINATIM",
                "pincode": pincode,
                "street_address": street_address,
                "formatted_address": formatted,
                "city": city,
                "state": state,
                "region": region,
                "lat": item.get("lat"),
                "lon": item.get("lon"),
            }
    except Exception as exc:
        logger.warning("Nominatim address lookup failed for %s, %s: %s", street_address, pincode, exc)
    return None


def _is_invalid_or_dummy_pincode(pincode: str) -> bool:
    """Strictly identify non-existent, dummy, or invalid Indian PIN codes."""
    pin = (pincode or "").strip()
    if len(pin) != 6 or not pin.isdigit():
        return True
    # 1. Invalid starting digits in India (Indian PIN codes start with digits 1 through 8 only)
    if pin.startswith(("0", "9")):
        return True
    # 2. Repeated digits (000000, 111111, 222222, 333333, 444444, 555555, 666666, 777777, 888888, 999999)
    if len(set(pin)) == 1:
        return True
    # 3. Known dummy / sequential pincodes
    if pin in {"123456", "654321", "234567", "345678", "456789", "567890", "987654"}:
        return True
    return False


def qualify(db: Session, pincode: str, street_address: str | None = None) -> dict:
    """Two-Step Location Qualification using OLA Maps API as Primary provider (and Nominatim fallback):
    Step 2A: Pincode Check -> Returns serviceable=True, requires_full_address=True (Plans NOT shown yet)
    Step 2B: Full Street Address Verification -> Returns address_qualified=True (Enables regional plans)
    """
    cleaned_pin = (pincode or "").strip()
    if _is_invalid_or_dummy_pincode(cleaned_pin):
        return {
            "found": False,
            "serviceable": False,
            "address_qualified": False,
            "pincode": cleaned_pin,
            "message": f"Sorry, PIN code {cleaned_pin} is invalid or not serviceable by Signal Selector Fiber. Please check your 6-digit PIN code and try again."
        }

    if street_address and street_address.strip():
        cleaned_street = clean_street_address(street_address, cleaned_pin) or street_address.strip()
        # Step 2B: Full Street Address Verification (Primary: OLA Maps, Secondary: Nominatim)
        geo = _olamaps_address_lookup(cleaned_street, cleaned_pin) or _nominatim_address_lookup(cleaned_street, cleaned_pin)
        if not geo:
            # Fallback using DB only if valid pincode exists in DB
            db_addr = db.scalar(select(Address).where(Address.pincode == cleaned_pin))
            if db_addr and db_addr.serviceable:
                region = get_telecom_circle(state=db_addr.state, city=db_addr.city, pincode=cleaned_pin)
                geo = {
                    "found": True,
                    "serviceable": True,
                    "address_qualified": True,
                    "provider": "TELECOM_CIRCLE_DB",
                    "pincode": cleaned_pin,
                    "street_address": cleaned_street,
                    "formatted_address": f"{cleaned_street}, {cleaned_pin}",
                    "city": db_addr.city,
                    "state": db_addr.state,
                    "region": region,
                }
            else:
                return {
                    "found": False,
                    "serviceable": False,
                    "address_qualified": False,
                    "pincode": cleaned_pin,
                    "message": f"Sorry, our fiber services are currently not available at PIN code {cleaned_pin}. We are expanding soon!"
                }
        
        state_prefix = (geo.get("state") or "REG")[:3].upper()
        fdh_id = f"FDH-{state_prefix}-01"
        geo.update({
            "fdh_id": fdh_id,
            "mst_id": f"MST-{state_prefix}-01",
            "olt_id": f"OLT-{state_prefix}-01",
            "max_speed_available_mbps": 1000,
            "requires_full_address": False,
            "message": f"Address verified for {geo['city']}, {geo['state']} ({geo['region']} Circle). Regional plans unlocked!"
        })
        return geo

    # Step 2A: Pincode Check Only (Primary: OLA Maps, Secondary: Nominatim)
    geo = _olamaps_pincode_lookup(cleaned_pin) or _nominatim_pincode_lookup(cleaned_pin)
    if not geo:
        db_addr = db.scalar(select(Address).where(Address.pincode == cleaned_pin))
        if db_addr and db_addr.serviceable:
            region = get_telecom_circle(state=db_addr.state, city=db_addr.city, pincode=cleaned_pin)
            geo = {
                "found": True,
                "serviceable": True,
                "pincode": cleaned_pin,
                "city": db_addr.city,
                "state": db_addr.state,
                "region": region,
                "fdh_id": db_addr.fdh_id,
            }
        else:
            return {
                "found": False,
                "serviceable": False,
                "address_qualified": False,
                "pincode": cleaned_pin,
                "message": f"Sorry, our fiber services are currently not available at PIN code {cleaned_pin}. We are expanding soon!"
            }

    state_prefix = (geo.get("state") or "REG")[:3].upper()
    geo.update({
        "requires_full_address": True,
        "address_qualified": False,
        "fdh_id": f"FDH-{state_prefix}-01",
        "max_speed_available_mbps": 1000,
        "message": f"Pincode {cleaned_pin} in {geo.get('city', 'Metro')}, {geo.get('state', 'Zone')} is in our service area! PIN code alone is not sufficient. Please provide your complete street address (house/flat no, street, locality) to view regional fiber plans."
    })
    return geo


def select_service_address(db: Session, pincode: str, speed_mbps: int) -> dict:
    address = db.scalar(select(Address).where(Address.pincode == pincode, Address.serviceable.is_(True)))
    if address:
        if address.max_speed_available_mbps < speed_mbps:
            raise ValueError("Selected plan speed is not available at this address")
        return {"pincode": address.pincode, "city": address.city, "state": address.state,
                "fdh_id": address.fdh_id, "mst_id": address.mst_id, "olt_id": address.olt_id}
    
    # Fallback for dynamic Nominatim addresses
    state_prefix = "REG"
    return {"pincode": pincode, "city": "Metro Circle", "state": "Telecom Circle",
            "fdh_id": f"FDH-{state_prefix}-01", "mst_id": f"MST-{state_prefix}-01", "olt_id": f"OLT-{state_prefix}-01"}
