import logging
import random
from app.assistant.llm import generate

logger = logging.getLogger(__name__)


def generate_dynamic_greeting() -> str:
    """Generate dynamic welcome greeting strictly using AI model prompt instructions."""
    styles = [
        "Greet the user warmly as Signal Selector's broadband AI assistant.",
        "Greet the user enthusiastically as Signal Selector's fiber connection guide.",
        "Provide a friendly, professional welcome as Signal Selector's broadband specialist.",
        "Give a concise, modern chat greeting introducing Signal Selector broadband assistance.",
    ]
    chosen_style = random.choice(styles)
    prompt = (
        f"{chosen_style} Ask if they have questions about plans, router specs, installation timelines, "
        "or if they would like to share their 6-digit PIN code to check local coverage. Keep it under 35 words. Do not use markdown."
    )
    try:
        llm_text = generate(prompt, temperature=0.95, timeout=6)
        if llm_text and len(llm_text.strip()) > 10:
            return llm_text.strip()
    except Exception as exc:
        logger.warning("Dynamic LLM greeting generation error: %s", exc)

    return "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."


