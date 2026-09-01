"""Modular assistant orchestration service for Signal Selector platform.

Architectural Workflow:
1. RAG FAQ Flow (Default): Answers general telecom FAQs, router specs, SLAs, and troubleshooting grounded strictly in data/faq_knowledge_base.md using pure LangChain RAG (no LangGraph).
2. Transition Guardrail: One-way state transition from RAG to ORDER_FLOW triggered by address/pincode input or explicit ordering intent. Once locked in ORDER_FLOW, session CANNOT revert to RAG.
3. Order Flow: Address qualification (Mapbox with Nominatim fallback) -> Regional plan cards -> LLM Plan Recommendation Assistant (Non-RAG) -> Customer Details -> Installation Appointment -> Payment & Order Creation.
"""
from __future__ import annotations

import logging
import re
from uuid import uuid4
from typing import Any

from sqlalchemy.orm import Session

from app.assistant.llm import generate, generate_json, classify_conversation_route
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
from app.services.welcome_service import generate_dynamic_greeting, generate_contextual_followups
from app.utils.trace import trace, trace_async

logger = logging.getLogger(__name__)


@trace
def _conversation_id(session: dict) -> str:
    conversation_id = session.get("conversation_id")
    if not conversation_id:
        conversation_id = f"CONV-{uuid4().hex[:12].upper()}"
        session["conversation_id"] = conversation_id
    return conversation_id


@trace
def _reset_address_state(session: dict) -> None:
    """Reset all address, qualification, and plan selection fields in session."""
    session["pincode"] = None
    session["street_address"] = None
    session["qualified_address"] = None
    session["address_qualified"] = False
    session["address_confirmed"] = False
    session["awaiting_address_confirmation"] = False
    session["awaiting_plan_permission"] = False
    session["plans_shown"] = False
    session["catalog_plans"] = []
    session["recommended_plans"] = []
    session["requires_full_address"] = False
    session["address_prompt_count"] = 0
    session["recommendation_stage"] = 0
    session["recommendation_answers"] = []


@trace
def _generate_address_confirmation_prompt(formatted_address: str) -> str:
    """Generate a dynamic 2-line LLM message: Line 1 asks to confirm address, Line 2 explains proceeding to plans."""
    prompt = (
        """Generate a short 2-line customer-facing message for a verified broadband service address.

Context:
formatted_address: {formatted_address}
- If formatted_address is missing or empty, refer to "your submitted address" and do not invent address details.

Requirements:
- Line 1: State that the address is verified as serviceable, and explicitly ask: "Is this your correct address?"
- Line 2: On a new line, state that confirming this allows us to proceed with showing the available fiber plans in your region.
- Line 1 MUST contain a question asking if the address is correct (ending with a question mark).
- Line 2 must be an explanatory statement starting with phrases like "So we can proceed...", "Once confirmed...", or "Confirming this allows us to...".
- Put Line 2 on its own line using a newline character.
- Do not mention booking, payment, appointments, or customer details.
- Maximum 35 words total.
- No markdown formatting.
"""
    ).format(
        formatted_address=formatted_address or ""
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=70)
        if text and len(text.strip()) > 10:
            cleaned = text.strip()
            if "\n" not in cleaned:
                cleaned = re.sub(r"(\.|\!|\?)\s+(So |Confirming |Once |This will |Proceeding )", r"\1\n\2", cleaned)
            lines = cleaned.split("\n")
            if "?" not in lines[0]:
                lines[0] = lines[0].rstrip(".") + ". Is this your correct address?"
                cleaned = "\n".join(lines)
            return cleaned
    except Exception as exc:
        logger.warning("LLM address confirmation prompt error: %s", exc)
    return f"Your address at {formatted_address} is verified as serviceable. Is this your correct address?\nConfirming this allows us to proceed with showing the available fiber plans in your region."


@trace
def _generate_plan_permission_prompt(formatted_address: str) -> str:
    """Generate a dynamic 1-sentence LLM question asking permission to show fiber plans."""
    prompt = (
        """Generate a short customer-facing question asking permission to show available fiber plans.

Context:
formatted_address: {formatted_address}
- If formatted_address is missing or empty, say "your confirmed address" and do not invent address details.

Requirements:
- Acknowledge that the address is confirmed.
- Ask whether to show available fiber plans for that location.
- Do not mention payment, booking, appointment, or customer details.
- Use one sentence.
- Maximum 20 words.
- No markdown.
"""
    ).format(
        formatted_address=formatted_address or ""
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=50)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM plan permission prompt error: %s", exc)
    return "Great! Address confirmed. Shall I show the available high-speed fiber plans for your location?"


@trace
def classify_confirmation_intent(message: str) -> str:
    """Classify user confirmation response into CONFIRM, DENY, or OTHER using LLM JSON mode."""
    prompt = """Classify the customer's response to the current yes/no broadband-flow question.

Context:
message: {message}
- If message is empty, vague, or unrelated to the yes/no question, classify it as OTHER.

Requirements:
- Return exactly one JSON object with one key named "intent".
- intent must be exactly one of: CONFIRM, DENY, OTHER.
- Use CONFIRM when the customer agrees, confirms, says the address is correct, asks to proceed, or asks to show plans.
- Use DENY when the customer disagrees, says the address is wrong, wants a different address, wants to change details, or cancels.
- Use OTHER for questions, ambiguous replies, mixed yes/no replies, or unrelated input.
- Do not include markdown, code fences, explanations, or extra keys.
- Maximum 60 characters.
""".format(message=message)
    try:
        data = generate_json(prompt, system="Return strict JSON with intent field only.", timeout=5)
        if data and data.get("intent") in {"CONFIRM", "DENY", "OTHER"}:
            return str(data.get("intent"))
    except Exception as exc:
        logger.warning("LLM confirmation intent classification error: %s", exc)

    low = message.lower().strip()
    words = set(re.findall(r"\b\w+\b", low))
    confirm_words = {"yes", "yeah", "yep", "sure", "ok", "okay", "correct", "confirm", "right", "show", "proceed", "agreed", "please"}
    deny_words = {"no", "nope", "wrong", "change", "incorrect", "different", "cancel"}

    if any(w in words for w in confirm_words):
        return "CONFIRM"
    if any(w in words for w in deny_words):
        return "DENY"
    return "OTHER"


@trace
def classify_plan_selection_intent(message: str) -> str:
    """Classify user intent during plan selection into RECOMMENDATION_REQUEST or FAQ_QUESTION using LLM JSON mode."""
    prompt = """Classify the customer's message during the plan selection stage of a broadband order.

Context:
message: {message}
- If message is empty, generic, or not clearly asking for help choosing a plan, classify it as FAQ_QUESTION.

Requirements:
- Return exactly one JSON object with one key named "intent".
- intent must be exactly one of: RECOMMENDATION_REQUEST, FAQ_QUESTION.
- Use RECOMMENDATION_REQUEST when the customer asks which plan is best, asks for a suggestion, or describes gaming, streaming, work-from-home, users, or devices to choose a plan.
- Use FAQ_QUESTION for pricing, installation, router, policy, offer, availability, or general follow-up questions.
- If both intents appear, prefer RECOMMENDATION_REQUEST only when the customer explicitly asks for a recommendation.
- Do not include markdown, code fences, explanations, or extra keys.
- Maximum 80 characters.
""".format(message=message)
    try:
        data = generate_json(prompt, system="Return strict JSON with intent field only.", timeout=5)
        if data and data.get("intent") in {"RECOMMENDATION_REQUEST", "FAQ_QUESTION"}:
            return str(data.get("intent"))
    except Exception as exc:
        logger.warning("LLM plan selection intent classification error: %s", exc)

    low = message.lower().strip()
    if any(w in low for w in ["recommend", "best", "gaming", "stream", "suggest", "which plan", "help me choose", "suitable", "question"]):
        return "RECOMMENDATION_REQUEST"
    return "FAQ_QUESTION"


@trace
def _generate_plans_unlocked_message(formatted_address: str, state_or_region: str, plan_count: int) -> str:
    """Generate a dynamic LLM message announcing regional plan cards unlocked with an enthusiastic achievement tone + follow-up question on next line."""
    prompt = (
        """Generate an enthusiastic, celebratory two-line customer-facing message announcing that regional fiber plans have been discovered and unlocked.

Context:
formatted_address: {formatted_address}
state_or_region: {state_or_region}
plan_count: {plan_count}
- If formatted_address is missing, refer to "your confirmed address".
- If state_or_region is missing, say "your region".
- If plan_count is 0 or missing, say "available fiber plan options" without claiming a number.

Requirements:
- Line 1 must sound joyful, positive, and celebrate the achievement of discovering high-speed fiber coverage for their location (e.g. "Great news!", "Fantastic news!", "Awesome news! High-speed fiber plans are available for {state_or_region} listed below.").
- Line 2 must ask: "Which plan suits you best, or would you like a recommendation?"
- Put Line 2 on a new line.
- Do not mention booking, payment, appointments, or customer details.
- Maximum 35 words total.
- No markdown.
"""
    ).format(
        formatted_address=formatted_address or "",
        state_or_region=state_or_region or "your region",
        plan_count=plan_count or 0,
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
    return f"Great news! We found high-speed fiber plans available for {state_or_region} listed below.\nWhich plan suits you best, or would you like a recommendation?"


@trace
def _generate_pincode_only_prompt(pincode: str, city: str | None = None, state: str | None = None) -> str:
    """Generate a dynamic LLM message when customer provides only a pincode, explaining complete address is required."""
    location_info = f"in {city}, {state}" if city and state else (f"in {city}" if city else "")
    prompt = (
        """Generate a short customer-facing message explaining that PIN-code-only input cannot complete premise qualification.

Context:
pincode: {pincode}
city: {city}
state: {state}
location_info: {location_info}
- If city or state is missing, omit that locality detail instead of inventing it.
- If pincode is missing, ask for both complete street address and a valid 6-digit PIN code.

Requirements:
- Politely confirm the PIN code area is eligible or pending exact premise verification.
- Make clear that the PIN code alone is insufficient.
- Ask for the complete street address: house/flat number, building name if available, street, and locality.
- Do not ask for plan selection, booking, payment, or appointment details.
- Maximum 35 words.
- No markdown.
"""
    ).format(
        pincode=pincode or "",
        city=city or "",
        state=state or "",
        location_info=location_info or "",
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=70)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM pincode-only prompt error: %s", exc)
    return (
        f"PIN code {pincode} {location_info} is in our service area! However, a PIN code alone is not sufficient. "
        "Please share your complete street address (house/flat number, building name, street, and locality) so we can verify exact coverage and unlock fiber plans."
    )


@trace
def _generate_prompt_complete_address(pincode: str | None = None) -> str:
    """Generate a dynamic LLM message requesting the customer's complete street address."""
    pin_context = f" for PIN code {pincode}" if pincode else ""
    prompt = (
        """Generate a short customer-facing message requesting the customer's complete service address.

Context:
pincode: {pincode}
pin_context: {pin_context}
- If pincode is provided, incorporate it naturally.
- If pincode is missing, ask for a valid 6-digit PIN code as part of the complete address.

Requirements:
- Request the complete address: house/flat number, street, locality, and PIN code.
- Make clear that both complete street address and PIN code are mandatory.
- Make clear that a PIN code alone is insufficient.
- Say the address will be used to check fiber availability and fetch local plans through our mapping provider.
- Do not ask for plan selection, booking, payment, or appointment details.
- Maximum 30 words.
- No markdown.
"""
    ).format(
        pincode=pincode or "",
        pin_context=pin_context,
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=65)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM complete address prompt error: %s", exc)
    return "Please share your complete street address (including house/flat number, street name, locality, and pincode) so we can verify exact coverage via Mapbox and show available fiber plans."


@trace
def _generate_invalid_pincode_message(pincode: str) -> str:
    """Generate a dynamic LLM response for invalid Indian postal PIN code input."""
    prompt = (
        """Generate a short customer-facing message for an invalid Indian postal PIN code.

Context:
pincode: {pincode}
- If pincode is empty, refer to "that PIN code" instead of quoting an empty value.

Requirements:
- State that the supplied PIN code is invalid.
- Explain that valid Indian PIN codes are 6 digits and start with digits 1 through 8.
- Ask for the complete street address with the correct PIN code.
- Do not mention serviceability, plans, booking, payment, or appointments.
- Maximum 30 words.
- No markdown.
"""
    ).format(
        pincode=pincode or ""
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=65)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM invalid pincode message error: %s", exc)
    return f"Sorry, PIN code '{pincode}' is invalid. Indian postal PIN codes are 6 digits starting with numbers 1 through 8. Please share your valid complete street address including correct PIN code."


@trace
def _generate_unserviceable_message(pincode: str, fallback_message: str | None = None) -> str:
    """Generate a dynamic LLM response for unserviceable location."""
    prompt = (
        """Generate a polite customer-facing message for a location where fiber service is unavailable.

Context:
pincode: {pincode}
fallback_message: {fallback_message}
- If pincode is missing, say "this area" instead of inventing a PIN code.
- If fallback_message contains a specific city or state, keep the meaning consistent but do not copy technical wording.

Requirements:
- State that fiber service is currently unavailable for the submitted area.
- Mention that coverage is expanding.
- Ask whether the customer wants to check a different complete street address with PIN code.
- Do not offer plans, booking, payment, or appointments.
- Maximum 30 words.
- No markdown.
"""
    ).format(
        pincode=pincode or "",
        fallback_message=fallback_message or "",
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=65)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM unserviceable message error: %s", exc)
    return fallback_message or f"Sorry, our fiber services are currently unavailable at PIN code {pincode}. We are expanding soon! Would you like to check a different complete street address?"


@trace
def _generate_escape_reset_message() -> str:
    """Generate a dynamic LLM response when user wants to reset or change address."""
    prompt = (
        """Generate a friendly customer-facing message acknowledging that the customer wants to reset or change address.

Context:
No interpolated variables are available for this message.
- Since no previous address should be reused, ask for a fresh complete address.

Requirements:
- Acknowledge the reset or address change.
- Ask for the complete street address: house/flat number, street, locality, and PIN code.
- Make clear that both address and PIN code are required for coverage verification.
- Do not mention plans, booking, payment, or appointments.
- Use one sentence.
- Maximum 25 words.
- No markdown.
"""
    )
    try:
        text = generate(prompt, temperature=0.7, timeout=5, max_tokens=60)
        if text and len(text.strip()) > 10:
            return text.strip()
    except Exception as exc:
        logger.warning("LLM escape reset message error: %s", exc)
    return "No problem! Let's start fresh. Please share your complete street address (house/flat number, street name, locality, and pincode)."


@trace
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
    followups = generate_contextual_followups(message="", answer=welcome, profile=profile)

    session["welcome"] = welcome
    session["recommended_followups"] = followups
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
        "recommended_followups": followups,
        "recommendedFollowups": followups,
        "mode": mode,
        "workflowState": workflow_state,
        "updatedState": updated_state,
    }


@trace
def _extract_pincode(text: str) -> str | None:
    """Extract a 6-digit Indian PIN code from text."""
    match = re.search(r"\b([1-9][0-9]{5})\b", text)
    if match:
        return match.group(1)
    return None


@trace
def _is_escape_intent(text: str) -> bool:
    """Detect if user wants to reset, change address, or leave the current sub-flow."""
    low = text.lower().strip()
    words = set(re.findall(r"\b\w+\b", low))
    if "no" in words or "nope" in words:
        return True
    escape_phrases = (
        "change address", "different address", "wrong address", "go back",
        "start over", "cancel", "reset", "new address", "change pincode",
        "different pincode", "other pincode", "change location",
    )
    return any(p in low for p in escape_phrases)


@trace
def _is_order_intent_trigger(text: str) -> bool:
    """Check if text expresses explicit intent to start an order or check serviceability."""
    low = text.lower().strip()
    if _extract_pincode(text):
        return True

    # 1. General info / plan inquiries stay in RAG flow unless explicit purchase/coverage intent is present
    info_inquiry_phrases = (
        "what are", "what is", "tell me", "show me", "how much", "which plan",
        "recommend", "compare", "options", "details", "explain", "plans available",
        "available plans", "list plans", "standard plans", "broadband plans", "what plans"
    )
    if any(q in low for q in info_inquiry_phrases) and not any(k in low for k in ["buy", "book", "purchase", "subscribe", "check coverage", "check serviceability", "new connection"]):
        return False

    # 2. Direct purchase action words or serviceability check keywords
    order_action_keywords = (
        "buy", "book", "purchase", "subscribe", "sign up", "get a new", "need a new",
        "i want a new", "want to buy", "want to book", "want to get", "check coverage",
        "check serviceability", "my pincode", "my address", "pincode is", "pin code is", "located at"
    )
    if any(w in low for w in order_action_keywords):
        return True

    # 3. Connection order phrases
    order_phrases = (
        "new connection", "new fiber", "new fibre", "order plan", "order fiber",
        "get fiber", "get broadband", "get a connection", "get new connection"
    )
    return any(p in low for p in order_phrases)


@trace
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


@trace
def handle_message(
    session_id: str,
    message: str,
    db: Session,
    *,
    language: str = "en",
    structured_fields: dict | None = None,
) -> dict:
    session = session_store.get(session_id)
    res = _handle_message_internal(
        session_id=session_id,
        message=message,
        db=db,
        language=language,
        structured_fields=structured_fields,
    )
    profile = session.get("profile", "general")
    ans = res.get("response", "")

    # Limit LLM response suggestions ONLY before entering order flow
    in_order_flow = bool(
        session.get("pincode") or
        session.get("address_qualified") or
        session.get("address_confirmed") or
        session.get("selected_plan") or
        session.get("customer") or
        session.get("appointment") or
        res.get("workflowState") in ["ADDRESS_QUALIFICATION", "ADDRESS_CONFIRMATION", "PLAN_SELECTION", "CUSTOMER_DETAILS", "APPOINTMENT", "PAYMENT", "ORDER_CONFIRMED"]
    )

    if not in_order_flow:
        followups = generate_contextual_followups(message=message, answer=ans, profile=profile)
    else:
        followups = []

    res["recommended_followups"] = followups
    res["recommendedFollowups"] = followups
    session["recommended_followups"] = followups
    return res


@trace
def _handle_message_internal(
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
    # If user asks to reset/change location or start over:
    if _is_escape_intent(message):
        was_in_order = (
            current_mode == "ORDER_FLOW"
            or session.get("awaiting_address_confirmation")
            or session.get("address_qualified")
            or session.get("pincode")
            or session.get("street_address")
        )
        _reset_address_state(session)
        if was_in_order:
            session["mode"] = "ORDER_FLOW"
            answer = _generate_escape_reset_message()
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
            session["mode"] = "RAG"
    elif current_mode == "ORDER_FLOW" or current_mode == "ORDER_COMPLETED":
        session["mode"] = "ORDER_FLOW"
    else:
        # 1. LLM-driven Intent Classifier (Primary route selection)
        try:
            llm_route = classify_conversation_route(message, session)
        except Exception as exc:
            logger.warning("Conversation route classification failed, using safety-net: %s", exc)
            llm_route = None
        if llm_route == "TRANSACTION":
            session["mode"] = "ORDER_FLOW"
            logger.info("LLM State transition: session=%s RAG -> ORDER_FLOW", session_id)
        elif llm_route == "KNOWLEDGE":
            session["mode"] = "RAG"
        elif _is_order_intent_trigger(message) or structured_fields or session.get("pincode") or session.get("requires_full_address"):
            # 2. Safety-net fallback if LLM route is inconclusive or API is offline
            session["mode"] = "ORDER_FLOW"
            logger.info("Safety-net State transition: session=%s RAG -> ORDER_FLOW", session_id)
        else:
            session["mode"] = "RAG"

    active_mode = session["mode"]

    # =========================================================================
    # FLOW 1: RAG FAQ FLOW (When mode is "RAG")
    # =========================================================================
    if active_mode == "RAG":
        try:
            retrieved_chunks = query_faq_collection(message, top_k=3)
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)
            retrieved_chunks = []
        try:
            answer = generate_grounded_faq_answer(message, retrieved_chunks)
        except Exception as exc:
            logger.warning("RAG synthesis failed: %s", exc)
            answer = "I can help with broadband plans, routers, installation, and coverage. Please ask a question, or share a complete street address with PIN code when you want to check serviceability."
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

    # Sub-step 1: Check for invalid PIN code input (only when input is a 6-digit number)
    if len(msg_strip) == 6 and msg_strip.isdigit() and _is_invalid_or_dummy_pincode(msg_strip):
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

    # Sub-step 1.5: Handle Address Confirmation Response
    if session.get("awaiting_address_confirmation"):
        confirm_intent = classify_confirmation_intent(message)
        if confirm_intent == "DENY":
            _reset_address_state(session)
            answer = _generate_escape_reset_message()
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
        elif confirm_intent == "CONFIRM":
            session["awaiting_address_confirmation"] = False
            session["address_confirmed"] = True
            session["awaiting_plan_permission"] = False
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

    # Sub-step 2: Address Verification & Geocoding via Mapbox with Nominatim fallback
    pincode = _extract_pincode(message) or session.get("pincode")
    street_address = session.get("street_address")

    if not re.fullmatch(r"\d{6}", msg_strip):
        if not re.search(r"\b(?:hi|hello|book|order|select|gaming|work|speed|price|plan)\b", msg_low):
            extracted = extract_street_address_llm(msg_strip, pincode)
            if extracted:
                street_address = extracted
                session["street_address"] = street_address

    # If street address is provided but PIN code is missing
    if street_address and not pincode and not session.get("address_qualified"):
        answer = f"Thank you! We received your street address at '{street_address}'. Please share the 6-digit PIN code for this location so we can check exact serviceability and fetch your regional fiber plans."
        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "PROMPT_PINCODE",
            "workflowState": "ADDRESS_QUALIFICATION",
            "response": answer,
            "sources": [],
            "canStartNewConnection": True,
            "updatedState": updated_state,
        }

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
            try:
                chunks = query_faq_collection(message, top_k=3)
            except Exception as exc:
                logger.warning("Order-flow FAQ retrieval failed: %s", exc)
                chunks = []
            if chunks:
                try:
                    faq_answer = generate_grounded_faq_answer(message, chunks)
                except Exception as exc:
                    logger.warning("Order-flow FAQ synthesis failed: %s", exc)
                    faq_answer = ""
                if not faq_answer:
                    faq_answer = "I can help with that from our broadband FAQs."
                if "whenever you're ready" not in faq_answer.lower() and "whenever you are ready" not in faq_answer.lower():
                    faq_answer = faq_answer.rstrip() + " You can share your complete street address whenever you're ready."
                answer = faq_answer
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
        reco_stage = session.get("recommendation_stage", 0)

        if reco_stage == 1:
            session["reco_users"] = message
            session["recommendation_stage"] = 2
            answer = "Got it! **Question 2 of 3:** How many devices (smartphones, laptops, smart TVs, gaming consoles) will be connected simultaneously?"
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PLAN_SELECTION",
                "workflowState": "PLAN_SELECTION",
                "response": answer,
                "sources": plans,
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

        elif reco_stage == 2:
            session["reco_devices"] = message
            session["recommendation_stage"] = 3
            answer = "Great! **Question 3 of 3:** What is your primary usage requirement? (e.g., 4K Streaming & Gaming, Work From Home, or General Browsing)"
            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PLAN_SELECTION",
                "workflowState": "PLAN_SELECTION",
                "response": answer,
                "sources": plans,
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

        elif reco_stage == 3:
            session["reco_purpose"] = message
            session["recommendation_stage"] = 0
            u_text = session.get("reco_users", "")
            d_text = session.get("reco_devices", "")
            p_text = session.get("reco_purpose", "")

            intro, reco_plan = recommend_plan_conversational(
                plans, message, users_text=u_text, devices_text=d_text, purpose_text=p_text
            )
            session["recommended_plan"] = reco_plan

            answer = f"{intro}\n\nWe recommend **{reco_plan.get('name')}** ({reco_plan.get('speed_mbps')} Mbps speed at ₹{reco_plan.get('price_inr')}/month), perfect for {u_text} users and {d_text} devices."

            updated_state = state_for_response(state_from_session(session_id, session))
            return {
                "sessionId": session_id,
                "conversationId": conversation_id,
                "mode": "ORDER_FLOW",
                "intent": "PLAN_RECOMMENDED",
                "workflowState": "PLAN_SELECTION",
                "response": answer,
                "sources": plans,
                "recommended_plan": reco_plan,
                "canStartNewConnection": True,
                "updatedState": updated_state,
            }

        reco_intent = classify_plan_selection_intent(message)
        if reco_intent == "RECOMMENDATION_REQUEST":
            session["recommendation_stage"] = 1
            answer = "I would be happy to recommend the perfect plan for you! Let's answer 3 quick questions.\n\n**Question 1 of 3:** How many people will be using this connection?"
        else:
            try:
                chunks = query_faq_collection(message, top_k=3)
                answer = generate_grounded_faq_answer(message, chunks)
            except Exception as exc:
                logger.warning("Plan-selection FAQ synthesis failed: %s", exc)
                answer = "Please tell me which plan you want, or ask me to recommend one."

        updated_state = state_for_response(state_from_session(session_id, session))
        return {
            "sessionId": session_id,
            "conversationId": conversation_id,
            "mode": "ORDER_FLOW",
            "intent": "PLAN_SELECTION",
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

