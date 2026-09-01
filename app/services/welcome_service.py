import logging
import random
from app.assistant.llm import generate, generate_json
from app.utils.trace import trace, trace_async

logger = logging.getLogger(__name__)


@trace
def generate_dynamic_greeting(profile: str = "general") -> str:
    """Generate dynamic welcome greeting strictly using AI model prompt instructions."""
    styles = [
        "Greet the user warmly as Signal Selector's broadband AI assistant.",
        "Greet the user enthusiastically as Signal Selector's fiber connection guide.",
        "Provide a friendly, professional welcome as Signal Selector's broadband specialist.",
        "Give a concise, modern chat greeting introducing Signal Selector broadband assistance.",
    ]
    chosen_style = random.choice(styles)

    if profile == "existing":
        prompt = (
            """Generate a concise customer-facing welcome greeting for an existing Signal Selector customer.

Context:
chosen_style: {chosen_style}
profile: {profile}
- If profile is existing, focus on current-account support and upgrades.

Requirements:
- Follow chosen_style naturally.
- Welcome the customer back to the Signal Selector portal.
- Ask how you can help with current plan, connection troubleshooting, router specs, or plan upgrades.
- Do not ask for address, PIN code, payment, booking, or appointment details.
- Maximum 35 words.
- No markdown.
"""
        ).format(
            chosen_style=chosen_style,
            profile=profile,
        )
    else:
        prompt = (
            """Generate a concise customer-facing welcome greeting for a new Signal Selector broadband visitor.

Context:
chosen_style: {chosen_style}
profile: {profile}
- If profile is missing or not existing, treat the visitor as a general new-service shopper.

Requirements:
- Follow chosen_style naturally.
- Offer help with plans, router specs, installation timelines, or serviceability.
- If mentioning serviceability, ask for a complete street address with building/flat number, street name, area, and PIN code.
- Do NOT ask for just a 6-digit pincode; ask for their complete street address.
- Mention that exact coverage and local plans are checked through our mapping provider.
- Do not mention payment, booking, or appointments.
- Maximum 35 words.
- No markdown.
"""
        ).format(
            chosen_style=chosen_style,
            profile=profile,
        )

    try:
        llm_text = generate(prompt, temperature=0.95, timeout=6, max_tokens=80)
        if llm_text and len(llm_text.strip()) > 10:
            return llm_text.strip()
    except Exception as exc:
        logger.warning("Dynamic LLM greeting generation error: %s", exc)

    if profile == "existing":
        return "Welcome back! I am your Signal Selector assistant. How can I help with your account, plan upgrades, or technical support today?"
    return "Welcome to Signal Selector! How can I help you today? Please share your complete street address (including building/flat number, street name, area, and pincode) so we can check exact fiber availability and fetch local plans."


@trace
def generate_contextual_followups(
    message: str = "",
    answer: str = "",
    profile: str = "general"
) -> list[str]:
    """Generate 3 dynamic contextual follow-up response options for the user strictly via LLM."""
    prompt = (
        """Generate 3 concise, highly relevant recommended user follow-up response options based on the conversation context.

Context:
profile: {profile}
user_previous_message: {message}
assistant_last_response: {answer}

Requirements:
- Return a JSON object with a single key "suggestions" containing an array of 3 short text strings (3 to 7 words each).
- The suggestions MUST mix natural first-person user action statements (such as "I want a new connection", "I want to book a connection", "I need a high-speed gaming plan", "I want to upgrade my plan") alongside relevant user queries.
- Do NOT make them all questions. Include clear intent statements like "I want to get a new fiber connection".
- All suggestions must be generated dynamically by the LLM based on the conversation context without static keyword templates.
- Return valid JSON only with key "suggestions".
"""
    ).format(
        profile=profile,
        message=message or "Chatbot opened / Initial Welcome",
        answer=answer or "Welcome greeting",
    )
    try:
        data = generate_json(prompt, system="Return strict JSON with suggestions array.", timeout=5)
        if data and isinstance(data.get("suggestions"), list) and len(data["suggestions"]) > 0:
            valid_suggestions = [str(s).strip() for s in data["suggestions"] if s and len(str(s).strip()) > 3]
            if len(valid_suggestions) >= 2:
                return valid_suggestions[:3]
    except Exception as exc:
        logger.warning("LLM follow-up suggestions generation error: %s", exc)

    if profile == "existing":
        return ["I want to upgrade my fiber plan", "Report a slow connection issue", "Show available add-on packs"]
    return ["I want to get a new connection", "I want to book a fiber plan", "Which plan is best for gaming & WFH?"]




