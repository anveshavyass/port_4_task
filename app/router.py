import time
import uuid
from typing import Any

from app.analytics import compute_sla_hours, find_duplicate_ticket
from app.logger import log_request, make_log_entry
from app.llm_client import LLMProviderError, call_model, repair_route
from app.schema import TicketRoute


def build_schema() -> dict[str, Any]:
    return TicketRoute.model_json_schema()


def _classify_with_llm(ticket_text: str, schema: dict[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        raw, provider, provider_error = call_model(ticket_text, schema)
        route = TicketRoute.model_validate(raw)
        result = route.model_dump()
        result["provider"] = provider
        if provider_error:
            result["provider_error"] = provider_error
        return result, "llm"
    except (ValueError, TypeError) as exc:
        invalid_response = None
        try:
            invalid_response = raw if 'raw' in locals() else None
        except NameError:
            invalid_response = None
        try:
            repaired, provider, provider_error = repair_route(ticket_text, schema, str(exc), invalid_response)
            route = TicketRoute.model_validate(repaired)
            result = route.model_dump()
            result["provider"] = provider
            if provider_error:
                result["provider_error"] = provider_error
            return result, "repair"
        except Exception:
            try:
                repaired, provider, provider_error = repair_route(ticket_text, schema, str(exc))
                route = TicketRoute.model_validate(repaired)
                result = route.model_dump()
                result["provider"] = provider
                if provider_error:
                    result["provider_error"] = provider_error
                return result, "repair"
            except Exception:
                model_confidence = 0.0
                if 'repaired' in locals() and isinstance(repaired, dict):
                    candidate = repaired.get("confidence")
                    if isinstance(candidate, (int, float)) and 0.0 <= candidate <= 1.0:
                        model_confidence = float(candidate)
                return {
                    "category": "Unclassified",
                    "priority": "Low",
                    "assigned_team": "Human Triage",
                    "reasoning": "Routing failed and the ticket requires human review.",
                    "confidence": model_confidence,
                    "system_wide_outage": False,
                    "provider": "openai",
                    "provider_error": str(exc),
                }, "fallback"
    except LLMProviderError as exc:
        if getattr(exc, "both_failed", False):
            reasoning = "Both OpenAI and Groq are unavailable. Please check your API keys and try again."
        else:
            reasoning = "The configured LLM provider is unavailable. Please check your OpenAI API key and try again."
        return {
            "category": "Unclassified",
            "priority": "Low",
            "assigned_team": "Human Triage",
            "reasoning": reasoning,
            "confidence": 0.0,
            "system_wide_outage": False,
            "provider": "openai",
            "provider_error": str(exc),
        }, "fallback"


def route_ticket(ticket_text: str) -> dict[str, Any]:
    ticket_id = uuid.uuid4().hex[:8]

    if not ticket_text or not ticket_text.strip():
        return {
            "ticket_id": ticket_id,
            "category": "Unclassified",
            "priority": "Low",
            "assigned_team": "Human Triage",
            "reasoning": "Please enter a ticket before routing.",
            "confidence": 0.0,
            "sla_hours": compute_sla_hours("Low"),
            "possible_duplicate_of": None,
            "system_wide_outage": False,
        }

    start = time.perf_counter()
    schema = build_schema()

    llm_result, llm_path = _classify_with_llm(ticket_text, schema)
    elapsed_ms = (time.perf_counter() - start) * 1000
    result = {
        "ticket_id": ticket_id,
        **llm_result,
        "sla_hours": compute_sla_hours(llm_result["priority"], llm_result.get("system_wide_outage", False)),
        "possible_duplicate_of": None,
    }
    duplicate = find_duplicate_ticket(ticket_text)
    if duplicate is not None:
        result["possible_duplicate_of"] = duplicate.get("ticket_id") or duplicate.get("input")
    log_request(make_log_entry(ticket_text, llm_path, elapsed_ms, result, ticket_id))
    return result
