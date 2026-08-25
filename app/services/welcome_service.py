import logging
import random
from app.assistant.llm import generate

logger = logging.getLogger(__name__)


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
            f"{chosen_style} Welcome an existing customer to the Signal Selector portal. Ask how you can assist "
            "with their current plan, connection troubleshooting, router specs, or plan upgrades. "
            "Keep it under 35 words total. Do not use markdown."
        )
    else:
        prompt = (
            f"{chosen_style} Ask if they have questions about plans, router specs, installation timelines, "
            "or if they would like to share their complete street address (including building/flat number, street name, area, and pincode) to check coverage and available fiber plans via Ola Maps API. "
            "Do NOT ask for just a 6-digit pincode; ask for their complete street address. Keep it under 35 words total. Do not use markdown."
        )

    try:
        llm_text = generate(prompt, temperature=0.95, timeout=6, max_tokens=80)
        if llm_text and len(llm_text.strip()) > 10:
            return llm_text.strip()
    except Exception as exc:
        logger.warning("Dynamic LLM greeting generation error: %s", exc)

    if profile == "existing":
        return "Welcome back! I am your Signal Selector assistant. How can I help with your account, plan upgrades, or technical support today?"
    return "Welcome to Signal Selector! How can I help you today? Please share your complete street address (including building/flat number, street name, area, and pincode) so we can check exact fiber availability and fetch local plans via Ola Maps."



