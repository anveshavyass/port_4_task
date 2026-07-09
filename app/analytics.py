import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from app.config import (
    CORRECTIONS_LOG_PATH,
    DUPLICATE_LOOKBACK_HOURS,
    DUPLICATE_SIMILARITY_THRESHOLD,
    REQUEST_LOG_PATH,
    RESOLUTIONS_LOG_PATH,
    SLA_HOURS,
)


def ensure_log_path(path_value: str) -> Path:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path_value: str, entry: dict[str, Any]) -> None:
    path = ensure_log_path(path_value)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def load_jsonl(path_value: str) -> list[dict[str, Any]]:
    path = Path(path_value)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        rows = []
        for line in handle:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def compute_sla_hours(priority: str) -> int:
    return int(SLA_HOURS.get(priority, 8))


def load_recent_request_history(lookback_hours: Optional[int] = None) -> list[dict[str, Any]]:
    lookback = lookback_hours if lookback_hours is not None else DUPLICATE_LOOKBACK_HOURS
    now = datetime.now(timezone.utc)
    entries = []
    for entry in load_jsonl(REQUEST_LOG_PATH):
        timestamp = parse_timestamp(entry.get("timestamp"))
        if timestamp and now - timestamp <= timedelta(hours=lookback):
            entries.append(entry)
    return entries


def find_duplicate_ticket(ticket_text: str, history_entries: Optional[list[dict[str, Any]]] = None) -> Optional[dict[str, Any]]:
    if not ticket_text or not ticket_text.strip():
        return None

    history = history_entries if history_entries is not None else load_recent_request_history()
    current = normalize_text(ticket_text)
    best_match: Optional[dict[str, Any]] = None

    for entry in history:
        previous_text = normalize_text(str(entry.get("input", "")))
        if not previous_text or previous_text == current:
            continue
        similarity = SequenceMatcher(None, current, previous_text).ratio()
        shared_tokens = set(current.split()) & set(previous_text.split())
        if similarity >= DUPLICATE_SIMILARITY_THRESHOLD or (len(shared_tokens) >= 2 and similarity >= 0.5):
            if best_match is None or similarity > best_match["similarity"]:
                best_match = {
                    "ticket_id": entry.get("ticket_id"),
                    "input": entry.get("input"),
                    "similarity": round(similarity, 2),
                }

    return best_match


def is_ticket_corrected(ticket_id: Optional[str]) -> bool:
    if not ticket_id:
        return False
    return any(entry.get("ticket_id") == ticket_id for entry in load_jsonl(CORRECTIONS_LOG_PATH))


def is_ticket_resolved(ticket_id: Optional[str]) -> bool:
    if not ticket_id:
        return False
    return any(entry.get("ticket_id") == ticket_id for entry in load_jsonl(RESOLUTIONS_LOG_PATH))


def log_correction(ticket_id: str, corrected_category: str, original_result: dict[str, Any], reason: str = "") -> bool:
    if is_ticket_corrected(ticket_id):
        return False
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticket_id": ticket_id,
        "corrected_category": corrected_category,
        "original_result": original_result,
        "reason": reason,
    }
    append_jsonl(CORRECTIONS_LOG_PATH, entry)
    return True


def record_resolution(ticket_id: str) -> bool:
    if is_ticket_resolved(ticket_id):
        return False
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticket_id": ticket_id,
    }
    append_jsonl(RESOLUTIONS_LOG_PATH, entry)
    return True


def build_stats() -> dict[str, Any]:
    request_entries = load_jsonl(REQUEST_LOG_PATH)
    resolution_entries = load_jsonl(RESOLUTIONS_LOG_PATH)
    correction_entries = load_jsonl(CORRECTIONS_LOG_PATH)
    resolved_ticket_ids = {entry.get("ticket_id") for entry in resolution_entries if entry.get("ticket_id")}

    category_counts = Counter(entry.get("output", {}).get("category", "Unclassified") for entry in request_entries if entry.get("output"))
    priority_counts = Counter(entry.get("output", {}).get("priority", "Medium") for entry in request_entries if entry.get("output"))

    latencies = [float(entry.get("latency_ms", 0.0)) for entry in request_entries if entry.get("latency_ms") is not None]
    avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    repair_count = sum(1 for entry in request_entries if entry.get("path_taken") == "repair")
    fallback_count = sum(1 for entry in request_entries if entry.get("path_taken") == "fallback")
    total_count = len(request_entries)

    overdue_count = 0
    now = datetime.now(timezone.utc)
    for entry in request_entries:
        output = entry.get("output", {}) or {}
        ticket_id = entry.get("ticket_id")
        if ticket_id in resolved_ticket_ids:
            continue
        timestamp = parse_timestamp(entry.get("timestamp"))
        if not timestamp:
            continue
        sla_hours = output.get("sla_hours", compute_sla_hours(output.get("priority", "Medium")))
        if now - timestamp > timedelta(hours=sla_hours):
            overdue_count += 1

    return {
        "total": total_count,
        "avg_latency_ms": avg_latency_ms,
        "repair_rate_pct": round((repair_count / total_count) * 100, 1) if total_count else 0.0,
        "fallback_rate_pct": round((fallback_count / total_count) * 100, 1) if total_count else 0.0,
        "correction_rate_pct": round((len(correction_entries) / total_count) * 100, 1) if total_count else 0.0,
        "category_counts": dict(category_counts),
        "priority_counts": dict(priority_counts),
        "overdue_count": overdue_count,
    }
