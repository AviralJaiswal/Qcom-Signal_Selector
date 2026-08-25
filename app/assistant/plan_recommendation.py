"""LLM-Powered Plan Recommendation Assistant (Non-RAG) inside the Order Flow."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.assistant.llm import generate

logger = logging.getLogger(__name__)


def recommend_plan_conversational(plans: list[dict[str, Any]], user_query: str) -> tuple[str, dict[str, Any] | None]:
    """Evaluate user's use case against active plans and return (intro_message, recommended_plan_dict)."""
    if not plans:
        return "Please verify your street address and PIN code to view available plans in your area.", None

    plans_context = []
    for idx, p in enumerate(plans, 1):
        plans_context.append(
            f"{idx}. Name: '{p.get('name')}' | Speed: {p.get('speed_mbps')} Mbps | Price: ₹{p.get('price_inr')}/month | ID: {p.get('plan_id')}"
        )

    context_str = "\n".join(plans_context)

    prompt = f"""You are Signal Selector's Telecom Plan Advisor.
Available Active Plans:
{context_str}

Task: Select the SINGLE best matching plan from the list above based on number of network users, connected devices, and primary purpose (such as 4K streaming, gaming, or work from home).
Return JSON ONLY in this format:
{{"recommended_plan_name": "exact plan name from list above", "short_intro": "Based on your requirements, here is the best recommended plan for you:"}}"""

    try:
        raw_res = generate(prompt, temperature=0.2, timeout=5, max_tokens=100)
        if raw_res:
            clean_res = raw_res.strip()
            if clean_res.startswith("```"):
                clean_res = clean_res.strip("`").removeprefix("json").strip()
            try:
                data = json.loads(clean_res)
                rec_name = (data.get("recommended_plan_name") or "").lower()
                intro = data.get("short_intro") or "Based on your requirements, here is the best recommended plan for you:"
                matched_plan = next((p for p in plans if p.get("name", "").lower() == rec_name or rec_name in p.get("name", "").lower()), None)
                if matched_plan:
                    return intro, matched_plan
            except Exception:
                pass
            for p in plans:
                if p.get("name", "").lower() in clean_res.lower():
                    return "Based on your requirements, here is the best recommended plan for you:", p
    except Exception as exc:
        logger.warning("Conversational plan recommendation failed: %s", exc)

    best_fallback = plans[1] if len(plans) > 1 else plans[0]
    return "Based on your requirements, here is the best recommended plan for you:", best_fallback

