"""LLM-Powered Plan Recommendation Assistant (Non-RAG) inside the Order Flow."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.assistant.llm import generate

logger = logging.getLogger(__name__)


def recommend_plan_conversational(plans: list[dict[str, Any]], user_query: str) -> str:
    """Evaluate user's use case against the 3-4 active regional plans using a dedicated prompt template (Non-RAG)."""
    if not plans:
        return "Please verify your street address and PIN code to view available plans in your area."

    plans_context = []
    for idx, p in enumerate(plans, 1):
        plans_context.append(
            f"{idx}. {p.get('name')} | Speed: {p.get('speed_mbps')} Mbps | Price: ₹{p.get('price_inr')}/month | "
            f"Type: {p.get('type', 'Fiber')} | Description: {p.get('description', '')} | "
            f"OTT Apps: {', '.join(p.get('ott_bundle', []))}"
        )

    context_str = "\n".join(plans_context)

    prompt = f"""You are Signal Selector's expert Telecom Plan Advisor assisting a customer in the active Order Flow.

Available Filtered Active Plans at Customer Location:
{context_str}

Customer Question / Use Case: "{user_query}"

ORCHESTRATION INSTRUCTIONS:
1. Evaluate the customer's specific use case (e.g. gaming, work from home, streaming, budget, large family) against ONLY the available active plans listed above.
2. Select the single best matching plan and explain WHY it fits their specific requirements in 2 to 3 clear, authoritative sentences.
3. Explicitly state the Plan Name, Speed (Mbps), Price (₹/month), and key benefits.
4. Do NOT recommend or mention any plans outside the list provided above.
5. End with a friendly sentence encouraging the customer to click the plan card to select and proceed with booking."""

    try:
        recommendation = generate(prompt, temperature=0.3, timeout=5)
        if recommendation and len(recommendation.strip()) > 20:
            return recommendation.strip()
    except Exception as exc:
        logger.warning("Conversational plan recommendation failed: %s", exc)

    return "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."

