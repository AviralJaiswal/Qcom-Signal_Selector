"""Modular assistant orchestration service for Signal Selector platform.

Architectural Workflow:
1. RAG FAQ Flow (Default): Answers general telecom FAQs, router specs, SLAs, and troubleshooting grounded strictly in data/faq_knowledge_base.md using pure LangChain RAG (no LangGraph).
2. Transition Guardrail: One-way state transition from RAG to ORDER_FLOW triggered by address/pincode input or explicit ordering intent. Once locked in ORDER_FLOW, session CANNOT revert to RAG.
3. Order Flow: Address qualification (Ola Maps API) -> Regional plan cards -> LLM Plan Recommendation Assistant (Non-RAG) -> Customer Details -> Installation Appointment -> Payment & Order Creation.
"""
from __future__ import annotations

import logging
import re
from uuid import uuid4
from typing import Any

from sqlalchemy.orm import Session

from app.assistant.llm import generate
from app.assistant.plan_recommendation import recommend_plan_conversational
from app.chat.session import session_store
from app.chat.state import state_for_response, state_from_session, ConversationState
from app.rag.chroma_rag import query_faq_collection, generate_grounded_faq_answer
from app.services.address_service import qualify, _is_invalid_or_dummy_pincode, clean_street_address, extract_street_address_llm
from app.services.appointment_service import available_slots, select_slot
from app.services.customer_service import find_or_validate
from app.services.order_service import create_order
from app.services.payment_service import create_purl, confirm_payment
from app.services.plan_service import recommend
from app.services.welcome_service import generate_dynamic_greeting

logger = logging.getLogger(__name__)


def _conversation_id(session: dict) -> str:
    conversation_id = session.get("conversation_id")
    if not conversation_id:
        conversation_id = f"CONV-{uuid4().hex[:12].upper()}"
        session["conversation_id"] = conversation_id
    return conversation_id


def _generate_address_confirmation_prompt(formatted_address: str) -> str:
    """Generate a dynamic 1-2 line LLM question asking user to confirm address before displaying plans."""
    prompt = (
        f"The user's street address has been verified as: '{formatted_address}'. "
        f"Write a 2-line message: Line 1: 'Is this address correct: {formatted_address}?' "
        "Line 2: 'Shall I show available fiber plans?' Keep it under 25 words total. No markdown."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=60)
        if text and len(text.strip()) > 10:
            res = text.strip()
            res = re.sub(r"\n+", "\n", res)
            if "?" in res and " Shall" in res:
                res = res.replace("? Shall", "?\nShall")
            elif "?" in res and " " in res:
                parts = res.split("?", 1)
                if len(parts) > 1 and parts[1].strip():
                    res = f"{parts[0]}?\n{parts[1].strip()}"
            return res
    except Exception as exc:
        logger.warning("LLM address confirmation prompt error: %s", exc)
    return f"Is this address correct: {formatted_address}?\nShall I show the available fiber plans for your area?"


def _generate_plans_unlocked_message(formatted_address: str, state_or_region: str, plan_count: int) -> str:
    """Generate a dynamic LLM message announcing regional plan cards unlocked + follow-up question on next line."""
    prompt = (
        f"The user confirmed their address at '{formatted_address}'. "
        f"Write Line 1: an enthusiastic sentence that {plan_count} fiber plans for {state_or_region} are listed below. "
        "Line 2 (ON A NEW LINE): ask 'Which plan suits you best, or would you like a recommendation?' Keep it under 30 words total."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=60)
        if text and len(text.strip()) > 10:
            cleaned = text.strip()
            cleaned = re.sub(r"(\.|\!|\?)\s+(Which|Would|Shall)", r"\1\n\2", cleaned)
            if "\n" not in cleaned:
                cleaned = re.sub(r"(\.|\!|\?)\s+", r"\1\n", cleaned, count=1)
            return cleaned
    except Exception as exc:
        logger.warning("LLM plans unlocked message error: %s", exc)
    return f"Great news! We have {plan_count} fantastic fiber plans for {state_or_region} listed below.\nWhich plan suits you best, or would you like a recommendation?"


def _generate_pincode_only_prompt(pincode: str, city: str | None = None, state: str | None = None) -> str:
    """Generate a dynamic LLM message when customer provides only a pincode, explaining complete address is required for Ola Maps geocoding."""
    location_info = f"in {city}, {state}" if city and state else (f"in {city}" if city else "")
    prompt = (
        f"The customer provided only the 6-digit PIN code '{pincode}' {location_info}. "
        "PIN code alone is not sufficient to qualify coverage and show fiber plans because Ola Maps API requires the complete street address. "
        "Acknowledge their PIN code area politely and explain that a 6-digit PIN code is not sufficient. "
        "Ask them to provide their complete street address (house/flat number, street name, and area/locality). "
        "Keep it under 35 words total. Do not use markdown."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=70)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM pincode-only prompt error: %s", exc)
    return (
        f"PIN code {pincode} {location_info} is in our service area! However, just a PIN code is not sufficient. "
        "Please share your complete street address (house/flat number, street name, and locality) so we can verify exact coverage with Ola Maps and unlock fiber plans."
    )


def _generate_prompt_complete_address(pincode: str | None = None) -> str:
    """Generate a dynamic LLM message requesting the customer's complete street address."""
    pin_context = f" for PIN code {pincode}" if pincode else ""
    prompt = (
        f"Ask the customer to provide their complete street address{pin_context} "
        "(including house/flat number, street name, locality, and pincode) to check fiber availability and fetch local plans via Ola Maps API. "
        "Emphasize that a complete street address is required, not just a PIN code. Keep it under 30 words total. Do not use markdown."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=65)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM complete address prompt error: %s", exc)
    return "Please share your complete street address (including house/flat number, street name, locality, and pincode) so we can verify exact coverage via Ola Maps and show available fiber plans."


def _generate_invalid_pincode_message(pincode: str) -> str:
    """Generate a dynamic LLM response for invalid Indian postal PIN code input."""
    prompt = (
        f"The user provided an invalid Indian postal PIN code '{pincode}'. "
        "Write a 1-2 sentence response explaining that valid Indian PIN codes are 6 digits starting with numbers 1 to 8, "
        "and ask them to share their valid complete street address including correct PIN code. Keep it under 30 words. No markdown."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=65)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM invalid pincode message error: %s", exc)
    return f"Sorry, PIN code '{pincode}' is invalid. Indian postal PIN codes are 6 digits starting with numbers 1 through 8. Please share your valid complete street address including correct PIN code."


def _generate_unserviceable_message(pincode: str, fallback_message: str | None = None) -> str:
    """Generate a dynamic LLM response for unserviceable location."""
    prompt = (
        f"The user requested fiber connection for PIN code '{pincode}', but our fiber network is not available there yet. "
        "Write a polite 1-2 sentence message stating we don't serve this area yet but are expanding, and ask if they'd like to check a different complete street address. Keep it under 30 words. No markdown."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=65)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM unserviceable message error: %s", exc)
    return fallback_message or f"Sorry, our fiber services are currently unavailable at PIN code {pincode}. We are expanding soon! Would you like to check a different complete street address?"


def _generate_escape_reset_message() -> str:
    """Generate a dynamic LLM response when user wants to reset or change address."""
    prompt = (
        "The customer wants to start over or change their address. "
        "Write a friendly 1-sentence response acknowledging the reset and asking them for their complete street address (house/flat number, street, locality, and pincode) to check coverage via Ola Maps. Keep it under 25 words. No markdown."
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=60)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM escape reset message error: %s", exc)
    return "No problem! Let's start fresh. Please share your complete street address (house/flat number, street name, locality, and pincode)."


def initialize_session(
    session_id: str | None = None,
    *,
    channel: str = "WEB",
    locale: str = "en-US",
    source: str = "SIGNAL_SELECTOR",
    profile: str = "general",
) -> dict:
    """Initialize a session and generate a fresh, dynamic welcome greeting."""
    session_id = session_id or f"SES-{uuid4().hex[:12].upper()}"
    session = session_store.create(session_id)
    conversation_id = _conversation_id(session)

    mode = "ORDER_FLOW" if profile == "existing" else "RAG"
    workflow_state = "EXISTING_CUSTOMER" if profile == "existing" else "RAG_FAQ"

    session.update({
        "mode": mode,
        "workflow_state": workflow_state,
        "channel": channel,
        "locale": locale,
        "source": source,
        "profile": profile,
        "address_qualified": False,
        "plans_shown": False,
    })

    welcome = generate_dynamic_greeting(profile=profile)

    session["welcome"] = welcome
    session.setdefault("conversation_history", []).append({"role": "assistant", "content": welcome, "kind": "welcome"})

    logger.info("Session initialized: session_id=%s, conversation_id=%s", session_id, conversation_id)
    updated_state = state_for_response(state_from_session(session_id, session))

    return {
        "sessionId": session_id,
        "conversationId": conversation_id,
        "channel": channel,
        "locale": locale,
        "source": source,
        "status": "ACTIVE",
        "response": welcome,
        "mode": mode,
        "workflowState": workflow_state,
        "updatedState": updated_state,
    }


def _extract_pincode(text: str) -> str | None:
    """Extract a 6-digit Indian PIN code from text."""
    match = re.search(r"\b([1-9][0-9]{5})\b", text)
    if match:
        return match.group(1)
    return None


def _is_escape_intent(text: str) -> bool:
    """Detect if user wants to reset, change address, or leave the current sub-flow."""
    low = text.lower().strip()
    escape_phrases = (
        "change address", "different address", "wrong address", "go back",
        "start over", "cancel", "reset", "new address", "change pincode",
        "different pincode", "other pincode", "change location",
    )
    return any(p in low for p in escape_phrases)


def _is_order_intent_trigger(text: str) -> bool:
    """Check if text expresses explicit intent to start an order or check serviceability."""
    low = text.lower()
    if _extract_pincode(text):
        return True

    # 1. Direct purchase action words or serviceability check keywords
    order_action_keywords = (
        "buy", "book", "purchase", "subscribe", "sign up", "get a new", "need a new",
        "i want a new", "want to buy", "want to book", "want to get", "check coverage",
        "check serviceability", "my pincode", "my address", "pincode is", "pin code is", "located at"
    )
    if any(w in low for w in order_action_keywords):
        return True

    # 2. General questions inquiring about plans/prices/options without purchase action stay in RAG
    question_starters = (
        "what", "tell me", "show me", "how much", "what is", "what are",
        "which plan", "recommend", "compare", "options", "details", "explain"
    )
    if any(q in low for q in question_starters):
        return False

    # 3. Connection order phrases
    order_phrases = (
        "new connection", "new fiber", "new fibre", "order plan", "order fiber",
        "get fiber", "get broadband", "get a connection", "get new connection"
    )
    return any(p in low for p in order_phrases)


def _extract_customer_info(text: str) -> dict:
    """Extract Name, Phone, and Email from message."""
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"(?<!\d)(?:\+91[- ]?)?([6-9]\d{9})(?!\d)", text)
    name_match = re.search(r"(?:name\s*[:\-]|name is|my name is|i am|i'm|^)\s*([A-Za-z][A-Za-z ]{1,50}?)(?=\s*[,;]|email|\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b|$)", text, re.I)

    name = name_match.group(1).strip(" .,!") if name_match else None
    if name and name.lower() in {"hi", "hello", "hey", "yes", "no", "order", "plan", "select"}:
        name = None

    return {
        "name": name,
        "phone": phone_match.group(1) if phone_match else None,
        "email": email_match.group(0) if email_match else None,
    }


def handle_message(
    session_id: str,
    message: str,
    db: Session,
    *,
    language: str = "en",
    structured_fields: dict | None = None,
) -> dict:
    """Canonical handler for user chat messages."""
    session = session_store.get(session_id)
    conversation_id = _conversation_id(session)
    current_mode = session.get("mode", "RAG")
    msg_strip = message.strip()
    msg_low = msg_strip.lower()

    # Apply structured field overrides if present
    if structured_fields:
        session.update({k: v for k, v in structured_fields.items() if v is not None})

    # ONE-WAY STATE MACHINE GUARDRAIL:
    # If user asks to reset/change location or start over, unlock RAG mode
    if _is_escape_intent(message):
        session["pincode"] = None
        session["street_address"] = None
        session["requires_full_address"] = False
        session["address_qualified"] = False
        session["address_confirmed"] = False
        session["awaiting_address_confirmation"] = False
        session["address_prompt_count"] = 0
        session["mode"] = "RAG"
    elif current_mode == "ORDER_FLOW" or current_mode == "ORDER_COMPLETED":
        session["mode"] = "ORDER_FLOW"
    elif _is_order_intent_trigger(message) or structured_fields or session.get("pincode") or session.get("requires_full_address"):
        session["mode"] = "ORDER_FLOW"
        logger.info("State transition: session=%s RAG -> ORDER_FLOW", session_id)
    else:
        session["mode"] = "RAG"

    active_mode = session["mode"]

    # =========================================================================
    # FLOW 1: RAG FAQ FLOW (When mode is "RAG")
    # =========================================================================
    if active_mode == "RAG":
        retrieved_chunks = query_faq_collection(message, top_k=3)
        answer = generate_grounded_faq_answer(message, retrieved_chunks)
        evidence = [{"type": "faq_chunk", "chunk": c} for c in retrieved_chunks]

        session.setdefault("conversation_history", []).extend([
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ])

        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "RAG",
            "intent": "FAQ_KNOWLEDGE",
            "workflowState": "RAG_FAQ",
            "response": answer,
            "sources": evidence,
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # =========================================================================
    # FLOW 2: ORDERING WORKFLOW (When mode is "ORDER_FLOW")
    # =========================================================================

    # Priority: If user is mid-recommendation-survey, process answer FIRST
    reco_stage = session.get("recommendation_stage", 0)
    if reco_stage > 0:
        plans = session.get("recommended_plans") or session.get("catalog_plans") or []
        answers = session.get("recommendation_answers", [])
        answers.append(msg_strip)
        session["recommendation_answers"] = answers
        reco_stage += 1
        session["recommendation_stage"] = reco_stage

        rec_plan = None
        if reco_stage == 2:
            answer = "Got it! Second, how many total devices will be connected to the network?"
        elif reco_stage == 3:
            answer = "Understood! Finally, what is your primary purpose for using the network (e.g., 4K streaming, online gaming, working from home, or smart home usage)?"
        else:
            user_query = f"Network Users: {answers[0]}. Connected Devices: {answers[1]}. Primary Purpose: {answers[2]}."
            answer, rec_plan = recommend_plan_conversational(plans, user_query)
            session["recommendation_stage"] = 0
            session["recommendation_answers"] = []

        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "PLAN_RECOMMENDATION",
            "workflowState": "PLAN_SELECTION",
            "response": answer,
            "recommendedPlan": rec_plan,
            "sources": [rec_plan] if rec_plan else plans,
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # Sub-step 1: Check for invalid PIN code input
    if _is_invalid_or_dummy_pincode(msg_strip) and re.fullmatch(r"\d+", msg_strip):
        answer = _generate_invalid_pincode_message(msg_strip)
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "INVALID_PINCODE",
            "workflowState": "ADDRESS_QUALIFICATION",
            "response": answer,
            "sources": [],
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # Sub-step 1.5: Handle Address Confirmation Response if awaiting confirmation
    if session.get("awaiting_address_confirmation"):
        if any(k in msg_low for k in ["no", "wrong", "change", "incorrect", "different"]):
            session["awaiting_address_confirmation"] = False
            session["address_qualified"] = False
            session["street_address"] = None
            session["plans_shown"] = False
            answer = _generate_prompt_complete_address()
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PROMPT_STREET_ADDRESS",
                "workflowState": "ADDRESS_QUALIFICATION",
                "response": answer,
                "sources": [],
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }
        else:
            session["awaiting_address_confirmation"] = False
            session["address_confirmed"] = True
            session["plans_shown"] = True
            plans = session.get("recommended_plans") or session.get("catalog_plans") or []
            qual = session.get("qualified_address") or {}
            formatted_addr = qual.get("formatted_address") or session.get("pincode", "")
            state_or_region = qual.get("state") or qual.get("region") or qual.get("city") or "your region"
            answer = _generate_plans_unlocked_message(formatted_addr, state_or_region, len(plans))
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PLANS_DISCOVERED",
                "workflowState": "PLAN_SELECTION",
                "response": answer,
                "sources": plans,
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

    # Sub-step 2: Address Verification & Geocoding via Ola Maps API
    pincode = _extract_pincode(message) or session.get("pincode")
    street_address = session.get("street_address")

    if pincode and not re.fullmatch(r"\d{6}", msg_strip):
        if not re.search(r"\b(?:hi|hello|book|order|select|gaming|work)\b", msg_low):
            extracted = extract_street_address_llm(msg_strip, pincode)
            if extracted:
                street_address = extracted
                session["street_address"] = street_address

    if pincode and not session.get("address_qualified"):
        qualification_result = qualify(db, pincode, street_address)
        session["qualified_address"] = qualification_result
        session["pincode"] = pincode
        session["serviceable"] = qualification_result.get("serviceable", False)

        if not qualification_result.get("serviceable"):
            answer = _generate_unserviceable_message(pincode, qualification_result.get("message"))
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "UNSERVICEABLE_LOCATION",
                "workflowState": "ADDRESS_QUALIFICATION",
                "response": answer,
                "sources": [],
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

        if qualification_result.get("requires_full_address") and not qualification_result.get("address_qualified"):
            session["requires_full_address"] = True
            session["address_qualified"] = False
            session["plans_shown"] = False
            session["catalog_plans"] = []
            session["recommended_plans"] = []
            addr_prompt_count = session.get("address_prompt_count", 0) + 1
            session["address_prompt_count"] = addr_prompt_count
            city = qualification_result.get("city")
            state_val = qualification_result.get("state")
            answer = _generate_pincode_only_prompt(pincode, city, state_val)
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PROMPT_STREET_ADDRESS",
                "workflowState": "ADDRESS_QUALIFICATION",
                "response": answer,
                "sources": [],
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

        if qualification_result.get("address_qualified"):
            session["address_qualified"] = True
            session["requires_full_address"] = False
            state_or_region = qualification_result.get("state") or qualification_result.get("region") or qualification_result.get("city")
            plans = recommend(db, qualification_result.get("max_speed_available_mbps", 1000), state_or_region=state_or_region)
            session["recommended_plans"] = plans
            session["catalog_plans"] = plans

            if not session.get("address_confirmed"):
                session["awaiting_address_confirmation"] = True
                session["address_confirmed"] = False
                session["plans_shown"] = False
                formatted_addr = qualification_result.get("formatted_address") or f"{street_address}, {pincode}"
                answer = _generate_address_confirmation_prompt(formatted_addr)
                updated_state = state_for_response(state_from_session(session_id, session))
                return {
                    "sessionId": session_id,
                    "conversationId": conversation_id,
                    "mode": "ORDER_FLOW",
                    "intent": "CONFIRM_ADDRESS_PROMPT",
                    "workflowState": "ADDRESS_CONFIRMATION",
                    "response": answer,
                    "sources": [],
                    "canStartNewConnection": True,
                    "updatedState": updated_state,
                }
            else:
                session["plans_shown"] = True
                plan_count = len(plans)
                answer = f"Your address at {qualification_result.get('formatted_address', pincode)} has been verified! Here are the {plan_count} active high-speed regional fiber plans available for {state_or_region}:"
                updated_state = state_for_response(state_from_session(session_id, session))
                return {
                    "sessionId": session_id,
                    "conversationId": conversation_id,
                    "mode": "ORDER_FLOW",
                    "intent": "PLANS_DISCOVERED",
                    "workflowState": "PLAN_SELECTION",
                    "response": answer,
                    "sources": plans,
                    "canStartNewConnection": True,
                    "updatedState": updated_state,
                }

    # Prompt for complete address if not provided yet in Order Flow
    if not pincode or not session.get("address_qualified"):
        # Check if user message is actually a FAQ/general question rather than an address
        if not re.search(r"\d{6}", msg_strip) and not clean_street_address(msg_strip, pincode):
            chunks = query_faq_collection(message, top_k=3)
            if chunks:
                faq_answer = generate_grounded_faq_answer(message, chunks)
                answer = f"{faq_answer}\n\n*(Note: Whenever you're ready to check local plan availability or book a connection, please share your PIN code or complete street address!)*"
                updated_state = state_for_response(state_from_session(session_id, session))
                return {
                    "sessionId": session_id,
                    "conversationId": conversation_id,
                    "mode": "ORDER_FLOW",
                    "intent": "FAQ_KNOWLEDGE",
                    "workflowState": "ADDRESS_QUALIFICATION",
                    "response": answer,
                    "sources": [{"type": "faq_chunk", "chunk": c} for c in chunks],
                    "canStartNewConnection": True,
                    "updatedState": updated_state,
                }

        answer = _generate_prompt_complete_address(pincode=pincode if session.get("requires_full_address") else None)
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "PROMPT_LOCATION",
            "workflowState": "ADDRESS_QUALIFICATION",
            "response": answer,
            "sources": [],
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # Sub-step 3: Plan Selection & LLM-Powered Plan Recommendation Assistant (Non-RAG)
    plans = session.get("recommended_plans") or session.get("catalog_plans") or []
    selected_plan = session.get("selected_plan")

    if structured_fields and structured_fields.get("selected_plan"):
        selected_plan = structured_fields["selected_plan"]
        session["selected_plan"] = selected_plan

    # Handle escape intent: user wants to change address or start over
    if not selected_plan and plans and _is_escape_intent(message):
        session["address_qualified"] = False
        session["address_confirmed"] = False
        session["street_address"] = None
        session["plans_shown"] = False
        session["requires_full_address"] = False
        session["pincode"] = None
        session["recommended_plans"] = []
        session["catalog_plans"] = []
        session["qualified_address"] = None
        session["address_prompt_count"] = 0
        session["recommendation_stage"] = 0
        session["recommendation_answers"] = []
        answer = _generate_escape_reset_message()
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "PROMPT_LOCATION",
            "workflowState": "ADDRESS_QUALIFICATION",
            "response": answer,
            "sources": [],
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    if not selected_plan and plans:
        # Check if user message selects a plan by name or ID
        for p in plans:
            p_name = (p.get("name") or "").lower()
            p_id = (p.get("plan_id") or "").lower()
            if p_name in msg_low or p_id in msg_low:
                selected_plan = p
                session["selected_plan"] = selected_plan
                break

    if not selected_plan and plans:
        # Check if user is asking for help or a recommendation
        plan_question_keywords = ["which", "recommend", "best", "gaming", "work", "wfh", "stream",
                                   "budget", "cheap", "difference", "compare", "suited", "good for",
                                   "fastest", "cheapest", "value", "family", "download", "upload",
                                   "ott", "netflix", "hotstar", "speed", "mbps", "help", "suggest"]
        is_plan_question = any(k in msg_low for k in plan_question_keywords)

        if is_plan_question:
            session["recommendation_stage"] = 1
            session["recommendation_answers"] = []
            answer = "I can help you find the best plan! Let me ask you 3 quick questions.\nFirst, how many users will be using the network?"
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PLAN_RECOMMENDATION",
                "workflowState": "PLAN_SELECTION",
                "response": answer,
                "sources": plans,
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

    if not selected_plan:
        answer = "Tap any plan card above to select it, or ask me something like 'which plan is best for gaming?' to get a recommendation!"
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "SELECT_PLAN",
            "workflowState": "PLAN_SELECTION",
            "response": answer,
            "sources": plans,
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # Sub-step 4: Customer Details Capture
    customer = session.get("customer") or {}
    extracted = _extract_customer_info(message)
    for k, v in extracted.items():
        if v and not customer.get(k):
            customer[k] = v

    if extracted.get("name") or extracted.get("email") or extracted.get("phone"):
        session["customer"] = customer

    missing_customer_fields = [f for f in ("name", "phone", "email") if not customer.get(f)]
    if missing_customer_fields:
        missing_str = ", ".join(f.capitalize() for f in missing_customer_fields)
        answer = f"You selected the **{selected_plan.get('name')}** plan (₹{selected_plan.get('price_inr')}/month). Please provide your {missing_str} to set up your account."
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "CAPTURE_CUSTOMER_DETAILS",
            "workflowState": "CUSTOMER_DETAILS",
            "response": answer,
            "sources": [],
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # Save validated customer profile
    try:
        validated_customer = find_or_validate(db, **customer)
        session["customer"] = validated_customer
    except Exception as exc:
        logger.warning("Customer validation warning: %s", exc)

    # Sub-step 5: Installation Appointment Selection
    appointment = session.get("appointment")
    slot_match = re.search(r"SLOT-[A-Z0-9:-]+", message.upper())
    fdh_id = (session.get("qualified_address") or {}).get("fdh_id") or "FDH-CHENNAI-01"

    if slot_match and not appointment:
        try:
            appointment = select_slot(db, slot_match.group(0), fdh_id)
            session["appointment"] = appointment
        except Exception as exc:
            logger.warning("Slot selection failed: %s", exc)

    if not appointment:
        slots = available_slots(db, fdh_id)
        answer = f"Thank you, {customer.get('name')}! Contact details saved. Please choose an installation appointment slot from the options below:"
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "SELECT_APPOINTMENT",
            "workflowState": "APPOINTMENT",
            "response": answer,
            "sources": slots,
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

    # Sub-step 6: Payment Confirmation & Order Creation
    payment = session.get("payment")
    if not payment:
        payment = create_purl(session_id, selected_plan.get("price_inr", 799))
        payment = confirm_payment(payment, "TXN-AUTO-CONFIRM")
        session["payment"] = payment
        session["payment_status"] = payment.get("status")

    if not session.get("order_id"):
        order_data = create_order(db, session_id, session)
        session["order_id"] = order_data.get("order_id")
        session["mode"] = "ORDER_COMPLETED"
        session["workflow_state"] = "COMPLETED"

        order_id = order_data.get("order_id")
        inst_date = (appointment or {}).get("date", "Tomorrow")
        inst_slot = (appointment or {}).get("time_window", "Morning")

        answer = (
            f"🎉 **Booking Confirmed!**\n\n"
            f"Congratulations {customer.get('name')}! Your order **{order_id}** has been confirmed successfully.\n\n"
            f"**Plan Details:**\n"
            f"• Plan: {selected_plan.get('name')} ({selected_plan.get('speed_mbps')} Mbps)\n"
            f"• Price: ₹{selected_plan.get('price_inr')}/month\n\n"
            f"**Customer Details:**\n"
            f"• Name: {customer.get('name')}\n"
            f"• Contact: {customer.get('phone')} | {customer.get('email')}\n\n"
            f"**Installation Details:**\n"
            f"• Date: {inst_date}\n"
            f"• Time: {inst_slot}\n\n"
            "Our technician will contact you prior to arrival."
        )
    else:
        answer = f"Your order **{session.get('order_id')}** is active and confirmed! If you have any further questions, feel free to reach out."

    updated_state = state_for_response(state_from_session(session_id, session))
    return {
        "sessionId": session_id,
        "conversationId": conversation_id,
        "mode": session["mode"],
        "intent": "ORDER_CONFIRMED",
        "workflowState": session.get("workflow_state", "COMPLETED"),
        "response": answer,
        "sources": [],
        "canStartNewConnection": True,
        "updatedState": updated_state,
    }

