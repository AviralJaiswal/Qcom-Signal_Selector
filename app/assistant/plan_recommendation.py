"""LLM-Powered Plan Recommendation Assistant (Non-RAG) inside the Order Flow."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.assistant.llm import generate
from app.utils.trace import trace, trace_async

logger = logging.getLogger(__name__)


@trace
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

    prompt = """Select the single best matching active broadband plan for the customer's stated usage needs.

Context:
available_plans:
{context_str}
user_query: {user_query}
- If user_query is incomplete, prefer the best balanced plan by speed and value.
- If two plans appear equally suitable, choose the lower monthly price.

Requirements:
- Return exactly one JSON object with keys "recommended_plan_name" and "short_intro".
- recommended_plan_name must exactly match one plan name from available_plans.
- Base the choice on number of users, connected devices, and primary purpose such as 4K streaming, gaming, work from home, or smart-home use.
- short_intro must be customer-facing, friendly, and no more than 18 words.
- Do not include markdown, code fences, explanations, rankings, or extra keys.
- Maximum 180 characters for the full JSON response.
""".format(context_str=context_str, user_query=user_query)

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

