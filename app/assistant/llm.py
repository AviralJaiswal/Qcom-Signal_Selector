"""Server-side OpenRouter LLM adapter shared by assistant features."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from app.config import get_settings
from app.services.http_client import requests_verify_setting

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Actionable OpenRouter failure with safe diagnostic details."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.model = model
        self.endpoint = endpoint
        self.retryable = retryable

    def user_message(self) -> str:
        if self.status_code == 402:
            return (
                "The AI assistant is temporarily unavailable due to account credit limits. "
                "Please try again later or contact support."
            )
        if self.status_code == 401:
            return "The AI assistant is misconfigured. Please contact support."
        if self.status_code == 429:
            return "The AI assistant is busy right now. Please try again in a moment."
        if self.status_code in {500, 502, 503}:
            return "The AI assistant encountered a temporary service error. Please try again."
        return "The AI assistant is temporarily unavailable. Please try again."


def _safe_response_body(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        return response.text[:2000]
    except Exception:
        return ""


def _raise_for_http_error(response: requests.Response, *, model: str | None = None, endpoint: str | None = None) -> None:
    status_code = response.status_code
    body = _safe_response_body(response)
    retryable = status_code in {429, 500, 502, 503, 504}
    msg = f"OpenRouter HTTP error {status_code}: {body[:200]}"
    raise LLMError(
        msg,
        status_code=status_code,
        response_body=body,
        model=model,
        endpoint=endpoint,
        retryable=retryable,
    )


def llm_available() -> bool:
    settings = get_settings()
    return bool(settings.gemini_api_key or settings.openrouter_api_key or settings.openai_api_key)


def _call_gemini_rest(
    messages: list[dict[str, str]],
    api_key: str,
    model: str = "gemini-2.5-flash",
    *,
    system: str | None = None,
    timeout: int = 8,
    temperature: float = 0.8,
) -> str | None:
    models_to_try = [model, "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    target_models = list(dict.fromkeys([m for m in models_to_try if m]))
    
    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": f"[System Instruction]: {system}"}]})
    for m in messages:
        role = "user" if m.get("role") in {"user", "system"} else "model"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})

    payload = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }

    for target_model in target_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        for verify_ssl in (requests_verify_setting(), False):
            try:
                res = requests.post(url, json=payload, timeout=min(timeout, 8), verify=verify_ssl)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                return text
            except Exception as exc:
                logger.warning("Gemini REST API attempt failed model=%s verify=%s err=%s", target_model, verify_ssl, exc)
    return None


def chat(
    messages: list[dict[str, str]],
    *,
    system: str | None = None,
    timeout: int = 20,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    raise_on_error: bool = False,
) -> str | None:
    """Return assistant text from Gemini or OpenRouter, or None when unavailable."""

    settings = get_settings()

    if not llm_available():
        logger.warning("LLM unavailable: no API key loaded in environment")
        if raise_on_error:
            raise LLMError("LLM is not configured")
        return None

    openrouter_key = settings.openrouter_api_key or (settings.gemini_api_key if settings.gemini_api_key and settings.gemini_api_key.startswith("sk-or-") else None)
    
    # 1. Try OpenRouter API if OpenRouter key is configured
    if openrouter_key:
        payload_messages: list[dict[str, str]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
        model = settings.llm_model if "/" in settings.llm_model else "openai/gpt-4o-mini"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.api_base_url,
            "X-Title": settings.app_name,
        }
        payload = {
            "model": model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens if max_tokens is not None else settings.llm_max_tokens,
        }

        for verify_ssl in (requests_verify_setting(), False):
            try:
                logger.info("Calling OpenRouter: model=%s url=%s verify=%s", model, url, verify_ssl)
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                    verify=verify_ssl,
                )

                if response.status_code >= 400:
                    if raise_on_error:
                        _raise_for_http_error(response, model=model, endpoint=url)
                    logger.warning("OpenRouter API non-200 response: status=%s body=%s", response.status_code, response.text[:200])
                    continue

                body = response.json()
                choices = body.get("choices")
                if not choices:
                    if raise_on_error:
                        raise LLMError(f"OpenRouter returned no choices. model={model} endpoint={url} body={body}")
                    continue

                content = choices[0].get("message", {}).get("content", "").strip()
                if content:
                    return content
                elif raise_on_error:
                    raise LLMError(f"OpenRouter returned empty message content. model={model} endpoint={url}")

            except (LLMError, requests.HTTPError):
                if raise_on_error:
                    raise
            except Exception as exc:
                logger.warning("OpenRouter API attempt failed verify=%s err=%s", verify_ssl, exc)
                if raise_on_error and verify_ssl == False:
                    raise LLMError(f"OpenRouter request error: {exc}") from exc

    # 2. Try Gemini REST API if GEMINI_API_KEY is available
    if settings.gemini_api_key and not settings.gemini_api_key.startswith("sk-or-"):
        res = _call_gemini_rest(
            messages,
            settings.gemini_api_key,
            model=settings.llm_model,
            system=system,
            timeout=timeout,
        )
        if res:
            return res

    if raise_on_error:
        raise LLMError("LLM call failed")
    return None


def generate(
    prompt: str,
    *,
    system: str | None = None,
    timeout: int = 20,
    temperature: float = 0.7,
    raise_on_error: bool = False,
) -> str | None:
    """Single-turn helper used by welcome, RAG, and routing."""
    return chat(
        [{"role": "user", "content": prompt}],
        system=system,
        timeout=timeout,
        temperature=temperature,
        raise_on_error=raise_on_error,
    )


def generate_json(
    prompt: str,
    *,
    system: str | None = None,
    timeout: int = 25,
    raise_on_error: bool = False,
) -> dict[str, Any] | None:
    """Ask the model for a JSON object and parse the first object found."""
    text = generate(
        prompt + "\n\nRespond with valid JSON only.",
        system=system or "You return strict JSON objects only, with no markdown fences.",
        timeout=timeout,
        temperature=0.2,
        raise_on_error=raise_on_error,
    )
    if not text:
        return None

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.warning("OpenRouter returned non-JSON payload: %s", text[:300])
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("OpenRouter returned invalid JSON: %s", text[:300])
        return None


def classify_conversation_route(message: str, session: dict) -> str | None:
    """Return TRANSACTION or KNOWLEDGE using strict JSON classification."""

    prompt = f"""Classify this customer message for a telecom broadband assistant.

Return JSON exactly like:
{{"route": "TRANSACTION"}}
or
{{"route": "KNOWLEDGE"}}

Allowed route values (strict): TRANSACTION, KNOWLEDGE

TRANSACTION covers:
- explicitly starting an order ("I want a new connection", "book now", "buy plan")
- submitting a 6-digit postal PIN code or full street address
- selecting a specific plan card to purchase/checkout
- providing customer name, phone, email, or appointment slot

KNOWLEDGE covers:
- asking which plan is best for video calls, work from home, gaming, or streaming
- general inquiries about broadband plans, prices, speeds, OTT benefits, routers, installation fees, policies, or troubleshooting
- any question asking for recommendations or explanations before deciding to order

Session mode: {session.get("mode")}
Workflow state: {session.get("workflow_state")}
Customer message: {message}"""

    parsed = generate_json(
        prompt,
        system="Return strict JSON with a single route field. No markdown.",
        timeout=12,
    )
    if parsed:
        route = str(parsed.get("route", "")).strip().upper()
        if route in {"TRANSACTION", "KNOWLEDGE"}:
            return route

    # Legacy token fallback when JSON parsing fails
    result = generate(
        prompt,
        system="Reply with only TRANSACTION or KNOWLEDGE.",
        timeout=12,
        temperature=0,
    )
    if not result:
        return None
    normalized = result.strip().upper()
    if "TRANSACTION" in normalized:
        return "TRANSACTION"
    if "KNOWLEDGE" in normalized:
        return "KNOWLEDGE"
    return None
