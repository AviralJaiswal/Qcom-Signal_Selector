import logging
import random
from app.assistant.llm import generate
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



