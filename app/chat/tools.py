"""Thin LangGraph-facing adapters over the existing domain services."""

from sqlalchemy.orm import Session

from app.services.address_service import qualify, select_service_address
from app.services.appointment_service import available_slots, select_slot
from app.services.customer_service import find_or_validate
from app.services.order_service import create_order
from app.services.payment_service import confirm_payment, create_purl
from app.services.plan_service import recommend


def qualify_address_tool(db: Session, pincode: str, street_address: str | None = None) -> dict:
    return qualify(db, pincode, street_address)


def retrieve_plans_tool(db: Session, pincode: str, filters: dict | None = None, state_or_region: str | None = None) -> list[dict]:
    address = qualify(db, pincode)
    if not address.get("serviceable"):
        return []
    filters = filters or {}
    region_key = state_or_region or address.get("state") or address.get("region")
    return recommend(db, address.get("max_speed_available_mbps"), filters.get("preference"), state_or_region=region_key, use_gemini_reasoning=False)


def customer_details_tool(db: Session, details: dict) -> dict:
    return find_or_validate(db, **details)


def service_address_tool(db: Session, pincode: str, plan: dict) -> dict:
    return select_service_address(db, pincode, plan["speed_mbps"])


def appointment_tool(db: Session, fdh_id: str, slot_id: str | None = None) -> dict:
    if slot_id:
        return select_slot(db, slot_id, fdh_id)
    return {"slots": available_slots(db, fdh_id)}


def payment_tool(session_id: str, plan: dict, payment: dict | None = None, confirm: bool = False) -> dict:
    if confirm and payment:
        return confirm_payment(payment)
    return create_purl(session_id, plan["price_inr"])


def order_creation_tool(db: Session, session_id: str, state: dict) -> dict:
    return create_order(db, session_id, state)


def validate_and_check_serviceability(db: Session, pincode: str, street_address: str | None = None) -> dict:
    """Tool 1: Validates the 6-digit Indian PIN code and checks regional fiber coverage."""
    import re
    cleaned = pincode.strip()
    if not re.fullmatch(r"\d{6}", cleaned):
        return {
            "status": "INVALID_FORMAT",
            "pincode": cleaned,
            "serviceable": False,
            "message": "Invalid PIN code. Please enter a valid 6-digit Indian PIN code."
        }
    res = qualify(db, cleaned, street_address)
    if not res.get("serviceable"):
        return {
            "status": "UNSERVICEABLE",
            "pincode": cleaned,
            "serviceable": False,
            "message": f"Sorry, our fiber services are currently not available at PIN code {cleaned}. We are expanding soon!"
        }
    city = res.get("city") or "your area"
    state_name = res.get("state") or "your state"
    return {
        "status": "SERVICEABLE",
        "pincode": cleaned,
        "serviceable": True,
        "city": city,
        "state": state_name,
        "region": res.get("region"),
        "qualified_address": res,
        "message": f"Great news! Pincode {cleaned} in {city}, {state_name} is serviceable!\nPlease share your complete flat/building and street address to fetch the best local plans."
    }


def get_regional_plans(db: Session, pincode: str, circle_id: str | None = None, address: str | None = None) -> list[dict]:
    """Tool 2: Retrieves region-specific fiber plans, speeds, and OTT bundles once address is provided."""
    return retrieve_plans_tool(db, pincode, state_or_region=circle_id)


def rag_knowledge_search(db: Session, query: str, limit: int = 5) -> list[dict]:
    """Tool 3: Semantic search over activity.jsonl and plan catalogs for dynamic, hallucination-free QA."""
    from app.rag.retriever import search_knowledge_base
    return search_knowledge_base(query, limit=limit)

