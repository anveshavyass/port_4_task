import json
from typing import Any, Optional

import requests

from app.config import OPENAI_API_KEY, OPENAI_MODEL

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


def _build_messages(ticket_text: str, repair_context: str = None, invalid_response: Any = None) -> list[dict[str, str]]:
    instructions = (
        "You are a support ticket router. Return only a single JSON object with the exact keys: "
        "category, priority, assigned_team, reasoning, confidence, sla_hours, possible_duplicate_of. "
        "Do not include any other fields, IDs, timestamps, descriptions, or metadata. "
        "Use one of the allowed categories exactly: Billing, Account Access, Bug Report, Feature Request, Integration/API, General Inquiry, or Unclassified. "
        "Use one of the allowed priorities exactly: High, Medium, Low. "
        "Use one of the allowed assigned teams exactly: Billing Ops, Identity & Access, Engineering, Product, Platform/API, Customer Success, or Human Triage. "
        "The assigned_team is determined ONLY by category, always exactly this mapping, never guessed case by case: "
        "Billing -> Billing Ops. Account Access -> Identity & Access. Bug Report -> Engineering. Feature Request -> "
        "Product. Integration/API -> Platform/API. General Inquiry -> Customer Success. Unclassified -> Human "
        "Triage. "
        "Assign priority based on the actual scope, completeness, and duration of the impact described, never on tone "
        "or word choice by itself: "
        "High means a system-wide outage, an issue affecting many users at once, active data loss, a security breach, "
        "a complete/total failure where the product or a whole feature is entirely unusable (e.g. 'nothing works', "
        "'completely broken', 'can't do anything'), an unresolved issue the user says has lasted multiple days "
        "with no fix, OR a single user's issue where the real-world stakes are severe even though only one user is "
        "affected: a large sum of money at risk — use $1,000 as the concrete line, an amount at or above that is "
        "severe-stakes High, an amount below it (e.g. a $200 mischarge, a $50 duplicate charge) is a routine billing "
        "error and stays Medium no matter how the user phrases it — or a business-critical, time-bound process fully "
        "blocked with a stated hard deadline (e.g. payroll due in 2 hours, a contract renewal deadline today). "
        "Judge this from concrete stakes actually stated in the ticket — a dollar amount at or above the $1,000 "
        "line, a named deadline, an explicit business-critical process — never from vague language like 'this is "
        "important', 'significant', or 'urgent attention' alone; a ticket describing a two- or three-hundred-dollar "
        "mischarge is routine and Medium, full stop, regardless of how the user or the reasoning text describes it. "
        "When a single user's business-critical process is blocked, say so "
        "accurately in reasoning (e.g. 'blocks this user's payroll deadline') — do not invent 'many users' or "
        "'affects everyone' language just because the stakes are high; the user count is still one, only the stakes "
        "are what make it High. The severe-stakes trigger requires an actual stated dollar amount or an actual "
        "stated hard deadline/business-critical process — it does NOT apply just because the user calls something "
        "urgent, annoying, or asks to fix it quickly. A single user who cannot access their account, with no dollar "
        "amount, no deadline, and no stated wider impact, is Medium even if written impatiently or with typos (e.g. "
        "'wen fix bug plz its verry anoying and i cant acess my acount' is Medium, not High — annoyance and typos "
        "are not stakes). "
        "Medium means a single user is blocked from one specific function (e.g. cannot log in, was billed incorrectly, "
        "hit one reproducible bug) but has a workaround path (password reset, refund, retry) that is still untried or "
        "would plausibly work, no wider impact, and no mention of the issue persisting for an extended time. "
        "A workaround only counts if the ticket does not say it already failed. If the ticket states the user already "
        "tried the standard workaround and it did NOT fix the issue (e.g. 'I reset my password but still can't log "
        "in'), that workaround is exhausted, not available — never write in reasoning that a workaround exists or "
        "'is possible' when the ticket itself says it was tried and failed. This is still a single-user, "
        "single-function issue with no stated wider impact, so it stays Medium unless the ticket also gives a High "
        "trigger (wider impact, total failure, multi-day duration, or the severe-stakes trigger above); the "
        "reasoning must instead say the standard self-service fix was already attempted and did not work, so it "
        "needs direct investigation rather than another self-service attempt. "
        "Low means general inquiries, feature requests, cosmetic issues, or tickets where the user says it is not urgent. "
        "Routine single-account issues like a forgotten password or one small duplicate charge are Medium, not High, "
        "unless the ticket also describes a wider outage, a total failure, an ongoing multi-day delay, or the "
        "severe-stakes trigger above (large dollar amount, business-critical deadline). "
        "Never assume the worst case when scope or duration is left vague or unstated — High requires one of the "
        "triggers above to be explicitly stated or unmistakably implied, not merely plausible. A short, vague "
        "message that names an unspecified thing as 'down' or 'broken' again, with no stated number of users, no "
        "stated duration, and no named feature, defaults to Medium at most (never High) purely on the word 'down' "
        "or 'broken' — e.g. 'u no y its down again fix pls asap!!' has no insult or profanity (not an anger signal "
        "either — see the anger-signal definition below) and gives no evidence of scope or duration beyond 'again', "
        "so it should NOT be High. "
        "First decide whether the ticket describes ANY concrete, identifiable problem — this includes broad claims "
        "like 'nothing works' or 'completely broken', not only narrow ones. A ticket has concrete content as long as "
        "it says what is failing, even vaguely; it only lacks concrete content when it is pure venting/insults with "
        "no description of any failure at all (e.g. 'broken' alone with zero elaboration, or 'THIS APP IS TRASH FIX "
        "IT NOW!!!!1!' which insults the app but never says what is wrong with it). "
        "Do not pattern-match on the word 'broken' or 'down' by itself — what matters is whether a specific thing is "
        "named as failing, not the word choice. 'my account is broken again, third time this month' names a specific "
        "thing (the account) and a pattern (recurring) — this IS concrete content (Case A, category Account Access "
        "or Bug Report as appropriate), even though it is phrased sarcastically ('Oh wonderful... really great "
        "service') and even though it reuses the word 'broken'. Sarcasm wrapped around a real, specific complaint is "
        "still concrete content; only the bare word with zero elaboration and no named subject is Case B. "
        "Any clear, answerable question or specific request (e.g. 'how do I change my profile picture') is ALWAYS "
        "concrete content, no matter how it is wrapped — an urgent-sounding tone, caps, or exclamation marks around "
        "a real question never turn it into Case B. Judge whether content exists from the substance of the request "
        "alone, before looking at tone at all; only apply the anger-signal check afterward, and only to tickets that "
        "already have no content by that substance-first test. "
        "Define an anger signal by WORD CHOICE, not punctuation: an anger signal exists only when the text contains "
        "actual hostile or contemptuous language — an insult ('trash', 'garbage', 'useless', 'pathetic'), profanity, "
        "or a phrase expressing contempt/outrage about the product or service ('ridiculous', 'unacceptable', 'this "
        "is a joke'). "
        "Exclamation marks, ALL CAPS, and casual urgency words ('asap', 'pls', 'now', 'urgent') are NEVER an anger "
        "signal by themselves, no matter how many there are — they can only reinforce an anger signal that hostile "
        "wording already established; punctuation, capitalization, or texting-style urgency on their own are just "
        "emphasis, not emotion. For example, 'u no y its down again fix pls asap!!' contains no insult, no "
        "profanity, and no contemptuous phrase — it is casual shorthand, NOT an anger signal, even with '!!' and "
        "'asap'. By contrast, 'THIS APP IS TRASH FIX IT NOW!!!!1!' IS an anger signal because 'trash' is an insult; "
        "the caps and exclamation marks reinforce it but are not what makes it angry. "
        "Random keyboard-mashing or unintelligible strings of letters/numbers (e.g. 'asdkjfh qwoieru 12345') are "
        "NEVER an anger signal — there is no hostile wording to detect, so punctuation or caps on top of gibberish "
        "is noise, not emotion. "
        "Repetition and pleading are ALSO NOT anger signals by themselves: a phrase repeated many times with no "
        "hostile wording (e.g. 'please help please help please help please help') is desperation or spam, not "
        "anger. "
        "Never write 'angry tone' in reasoning unless actual hostile wording (insult, profanity, or contempt "
        "phrase) is present in the text — not merely because of punctuation, capitalization, or urgency words. "
        "Case A — ticket has concrete content (per the definition above): classify normally using the category and "
        "the High/Medium/Low scope-and-duration rubric above, regardless of tone, and ALWAYS assign a real category "
        "and matching team (Billing Ops, Identity & Access, Engineering, Product, Platform/API, or Customer "
        "Success) — never Unclassified/Human Triage in this case, even under an urgent-sounding priority. A broad "
        "'nothing works'/'everything is broken' claim about the product itself (with no billing, login, or feature "
        "request angle) defaults to category Bug Report, team Engineering. If anger signals are also present, keep "
        "the content-based category/priority/team and just add one sentence in reasoning noting the angry tone as "
        "context; anger and urgent-sounding language NEVER raise or lower the priority level itself in Case A — "
        "priority still comes only from the scope/completeness/duration rubric above. For example, a calm how-to "
        "question about changing a profile picture and the same question written as 'URGENT!!! how do I change my "
        "profile picture' get the exact same Low priority, because nothing about the actual scope or duration "
        "changed — only the reasoning sentence differs, by adding a note about the tone. "
        "Case B — ticket has NO concrete content at all: set category to Unclassified and assigned_team to Human "
        "Triage, confidence to 0.0. Then check for anger signals only to decide priority: if anger signals are "
        "present, set priority to High and explain in reasoning that no specific issue could be identified but the "
        "angry tone means a human should follow up promptly; if no anger signals are present, set priority to Low "
        "and explain in reasoning what information is missing, with no tone comment. "
        "For any ticket that is calm/neutral (no anger signals), never mention tone or sentiment in reasoning at all. "
        "If a ticket describes more than one issue, pick the category and priority for the single most impactful "
        "issue described, mention the other issue(s) briefly in reasoning, and do not add priority levels together. "
        "The reasoning field should be a short explanation of why this routing decision was made, following the tone "
        "rules above. "
        "The confidence field should be a number between 0.0 and 1.0. "
        "The sla_hours field should be an integer. "
        "The possible_duplicate_of field should be null if there is no duplicate. "
        "If the ticket is understandable but genuinely ambiguous between two categories, pick the closer match, "
        "keep confidence below 0.6, and say in reasoning which other category was considered. "
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


def call_openai(ticket_text: str, schema: dict[str, Any], repair_context: str = None, invalid_response: Any = None) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise LLMProviderError("OPENAI_API_KEY is not configured")

    payload = {
        "model": OPENAI_MODEL,
        "messages": _build_messages(ticket_text, repair_context, invalid_response),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMProviderError(f"OpenAI is unavailable: {str(exc)}") from exc

    data = response.json()
    raw_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if raw_text == "":
        raise LLMProviderError("OpenAI responded without content")

    try:
        return _parse_model_response(raw_text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMProviderError(f"OpenAI returned invalid JSON: {exc}") from exc


def call_model(ticket_text: str, schema: dict[str, Any]) -> tuple[dict[str, Any], str, Optional[str]]:
    return call_openai(ticket_text, schema), "openai", None


def repair_route(ticket_text: str, schema: dict[str, Any], validation_error: str, invalid_response: Any = None) -> tuple[dict[str, Any], str, Optional[str]]:
    repair_context = (
        "The previous response failed validation. Fix it and return valid JSON matching the schema exactly. "
        f"Validation error: {validation_error}"
    )
    return call_openai(ticket_text, schema, repair_context, invalid_response), "openai", None
