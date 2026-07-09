import json
from typing import Any, Optional

import requests

from app.config import GROQ_API_KEY, GROQ_MODEL, MODEL_NAME, OLLAMA_HOST, ROUTER_PROVIDER

ALLOWED_CATEGORIES = [
    "Billing",
    "Account Access",
    "Bug Report",
    "Feature Request",
    "Integration/API",
    "General Inquiry",
    "Unclassified",
]
ALLOWED_PRIORITIES = ["High", "Medium", "Low"]
ALLOWED_TEAMS = [
    "Billing Ops",
    "Identity & Access",
    "Engineering",
    "Product",
    "Platform/API",
    "Customer Success",
    "Human Triage",
]


class LLMProviderError(RuntimeError):
    pass


class OllamaUnavailableError(LLMProviderError):
    pass


def _build_messages(ticket_text: str, repair_context: str = None, invalid_response: Any = None) -> list[dict[str, str]]:
    instructions = (
        "You are a support ticket router. Return only a single JSON object with the exact keys: "
        "category, priority, assigned_team, reasoning, confidence, sla_hours, possible_duplicate_of. "
        "Do not include any other fields, IDs, timestamps, descriptions, or metadata. "
        "Use one of the allowed categories exactly: Billing, Account Access, Bug Report, Feature Request, Integration/API, General Inquiry, or Unclassified. "
        "Use one of the allowed priorities exactly: High, Medium, Low. "
        "Use one of the allowed assigned teams exactly: Billing Ops, Identity & Access, Engineering, Product, Platform/API, Customer Success, or Human Triage. "
        "The reasoning field should be a short explanation of why this routing decision was made. "
        "The confidence field should be a number between 0.0 and 1.0. "
        "The sla_hours field should be an integer. "
        "The possible_duplicate_of field should be null if there is no duplicate. "
        "If the ticket text is too short or vague to identify a real issue (e.g. one word, or no noun/verb "
        "describing a problem), set category to Unclassified, assigned_team to Human Triage, confidence to 0.0, "
        "and explain in reasoning what information is missing. "
        "Return valid JSON only, with no surrounding markdown or commentary."
    )

    if repair_context:
        system_prompt = f"{instructions} Fix the previous response to match the schema exactly."
        invalid_response_text = ""
        if invalid_response is not None:
            invalid_response_text = f"\nInvalid response: {json.dumps(invalid_response, default=str)}"
        user_prompt = f"{repair_context}{invalid_response_text}\nTicket: {ticket_text}"
    else:
        system_prompt = instructions
        user_prompt = f"Ticket: {ticket_text}"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _parse_model_response(raw_text: Any) -> dict[str, Any]:
    if isinstance(raw_text, dict):
        return raw_text
    if isinstance(raw_text, str):
        return json.loads(raw_text)
    raise ValueError("Unexpected model response type")


def call_ollama(ticket_text: str, schema: dict[str, Any], repair_context: str = None, invalid_response: Any = None) -> dict[str, Any]:
    payload = {
        "model": MODEL_NAME,
        "prompt": "\n".join([message["content"] for message in _build_messages(ticket_text, repair_context, invalid_response)]),
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.1},
    }

    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaUnavailableError(f"Ollama is unavailable: {str(exc)}") from exc

    data = response.json()
    raw_text = data.get("response", "")
    if not raw_text:
        raise OllamaUnavailableError("Ollama responded without content")

    try:
        return _parse_model_response(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise OllamaUnavailableError(f"Ollama returned invalid JSON: {exc}") from exc


def call_groq(ticket_text: str, schema: dict[str, Any], repair_context: str = None, invalid_response: Any = None) -> dict[str, Any]:
    if not GROQ_API_KEY:
        raise LLMProviderError("GROQ_API_KEY is not configured")

    payload = {
        "model": GROQ_MODEL,
        "messages": _build_messages(ticket_text, repair_context, invalid_response),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMProviderError(f"Groq is unavailable: {str(exc)}") from exc

    data = response.json()
    raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if raw_text == "":
        raise LLMProviderError("Groq responded without content")

    try:
        return _parse_model_response(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMProviderError(f"Groq returned invalid JSON: {exc}") from exc


def call_model(ticket_text: str, schema: dict[str, Any]) -> tuple[dict[str, Any], str, Optional[str]]:
    if ROUTER_PROVIDER == "ollama":
        return call_ollama(ticket_text, schema), "ollama", None

    try:
        return call_groq(ticket_text, schema), "groq", None
    except LLMProviderError as groq_exc:
        try:
            return call_ollama(ticket_text, schema), "ollama", str(groq_exc)
        except LLMProviderError as ollama_exc:
            raise LLMProviderError(f"Groq failed: {groq_exc}; Ollama failed: {ollama_exc}") from ollama_exc


def repair_route(ticket_text: str, schema: dict[str, Any], validation_error: str, invalid_response: Any = None) -> tuple[dict[str, Any], str, Optional[str]]:
    repair_context = (
        "The previous response failed validation. Fix it and return valid JSON matching the schema exactly. "
        f"Validation error: {validation_error}"
    )
    if ROUTER_PROVIDER == "ollama":
        return call_ollama(ticket_text, schema, repair_context, invalid_response), "ollama", None

    try:
        return call_groq(ticket_text, schema, repair_context, invalid_response), "groq", None
    except LLMProviderError as groq_exc:
        try:
            return call_ollama(ticket_text, schema, repair_context, invalid_response), "ollama", str(groq_exc)
        except LLMProviderError as ollama_exc:
            raise LLMProviderError(f"Groq repair failed: {groq_exc}; Ollama repair failed: {ollama_exc}") from ollama_exc
