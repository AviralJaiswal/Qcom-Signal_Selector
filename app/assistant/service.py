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
from app.rag.chroma_rag import query_faq_collection, generate_grounded_faq_answer, is_plan_pricing_inquiry
from app.services.address_service import qualify, _is_invalid_or_dummy_pincode
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
    is_existing = profile == "existing"

    mode = "ORDER_FLOW" if is_existing else "RAG"
    workflow_state = "EXISTING_CUSTOMER" if is_existing else "RAG_FAQ"

    session.update({
        "mode": mode,
        "workflow_state": workflow_state,
        "channel": channel,
        "locale": locale,
        "source": source,
        "is_existing_customer": is_existing,
        "address_qualified": False,
        "plans_shown": False,
    })

    if is_existing:
        prompt = (
            "You are Signal Selector Customer Support. Generate one short, friendly welcome message "
            "for an existing customer. Ask them to share their Name and Email address to look up their account."
        )
        try:
            welcome = generate(prompt, temperature=0.8) or "Welcome back to Signal Selector! Please share your Name and Email address so I can look up your subscription."
        except Exception:
            welcome = "Welcome back to Signal Selector! Please share your Name and Email address so I can look up your subscription."
    else:
        try:
            welcome = generate_dynamic_greeting()
        except Exception:
            welcome = "Welcome to Signal Selector! How can I assist you with our fiber broadband plans today?"

    session["welcome"] = welcome
    session.setdefault("conversation_history", []).append({"role": "assistant", "content": welcome, "kind": "welcome"})

    logger.info("Session initialized: session_id=%s, conversation_id=%s, profile=%s", session_id, conversation_id, profile)
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


def _is_order_intent_trigger(text: str) -> bool:
    """Check if text expresses explicit intent to start an order or check serviceability."""
    low = text.lower()
    if _extract_pincode(text):
        return True
    order_phrases = (
        "new connection", "fiber connection", "fibre connection", "new fiber", "new fibre",
        "buy plan", "order plan", "book connection", "get fiber", "get broadband",
        "subscribe", "sign up", "order fiber", "check pincode", "check address", "check serviceability",
        "my address", "pincode is", "pin code is", "located at"
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
    # If session is already in ORDER_FLOW, it STAYS locked in ORDER_FLOW.
    # Otherwise, check if user message triggers transition from RAG to ORDER_FLOW.
    if current_mode == "ORDER_FLOW" or current_mode == "ORDER_COMPLETED":
        session["mode"] = "ORDER_FLOW"
    elif _is_order_intent_trigger(message) or structured_fields:
        session["mode"] = "ORDER_FLOW"
        logger.info("State transition: session=%s RAG -> ORDER_FLOW", session_id)
    else:
        session["mode"] = "RAG"

    active_mode = session["mode"]

    # =========================================================================
    # FLOW 1: RAG FAQ FLOW (When mode is "RAG")
    # =========================================================================
    if active_mode == "RAG":
        # Check scope restriction: If user asks for specific regional pricing or plan recommendations in RAG mode
        if is_plan_pricing_inquiry(message):
            answer = (
                "Specific regional plans, pricing, and package speeds depend on network coverage at your exact location. "
                "The RAG FAQ service provides answers to general technical and service questions. "
                "To view, compare, and get recommendations for active plans at your location, please share your full street address and 6-digit PIN code!"
            )
            evidence = []
        else:
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

    # Sub-step 1: Check for invalid PIN code input
    if _is_invalid_or_dummy_pincode(msg_strip) and re.fullmatch(r"\d+", msg_strip):
        answer = f"Sorry, PIN code '{msg_strip}' is invalid or not serviceable. Indian postal PIN codes must be 6 digits starting with numbers 1 through 8. Please enter a valid 6-digit PIN code."
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

    # Sub-step 2: Address Verification & Geocoding via Ola Maps API
    pincode = _extract_pincode(message) or session.get("pincode")
    street_address = session.get("street_address")

    if not street_address and pincode and not re.fullmatch(r"\d{6}", msg_strip):
        if not any(k in msg_low for k in ["hi", "hello", "book", "order", "select", "gaming", "work"]):
            street_address = msg_strip
            session["street_address"] = street_address

    if pincode and not session.get("address_qualified"):
        qualification_result = qualify(db, pincode, street_address)
        session["qualified_address"] = qualification_result
        session["pincode"] = pincode
        session["serviceable"] = qualification_result.get("serviceable", False)

        if not qualification_result.get("serviceable"):
            answer = qualification_result.get("message") or f"Sorry, our fiber services are currently unavailable at PIN code {pincode}. We are expanding soon!"
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
            answer = f"Great news! Pincode {pincode} in {qualification_result.get('city', 'your area')}, {qualification_result.get('state', '')} is serviceable! Please provide your complete street address (house/flat number and street name) to unlock regional fiber plans."
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

    # Prompt for pincode & address if not provided yet in Order Flow
    if not pincode or not session.get("address_qualified"):
        answer = "To check broadband serviceability and unlock regional fiber plans, please share your 6-digit area PIN code and complete street address."
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
        # Check if user is asking conversational questions about the presented plans (Non-RAG)
        is_plan_question = any(k in msg_low for k in ["which", "recommend", "best", "gaming", "work", "wfh", "stream", "budget", "cheap", "difference", "compare", "suited", "good for"])
        if is_plan_question or len(msg_strip.split()) >= 3:
            answer = recommend_plan_conversational(plans, message)
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
        answer = "Please select one of the plan cards above to proceed with your order, or ask me which plan fits your specific needs!"
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
        inst_slot = (appointment or {}).get("slot", "Morning")

        answer = (
            f"🎉 Congratulations {customer.get('name')}! Your order **{order_id}** for **{selected_plan.get('name')}** "
            f"has been confirmed successfully! Installation is scheduled for {inst_date} ({inst_slot}). "
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

