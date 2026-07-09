import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import REQUEST_LOG_PATH


def ensure_log_path() -> Path:
    path = Path(REQUEST_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_request(entry: dict[str, Any]) -> None:
    path = ensure_log_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def make_log_entry(ticket_text: str, path_taken: str, latency_ms: float, output: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticket_id": ticket_id,
        "input": ticket_text,
        "path_taken": path_taken,
        "latency_ms": round(latency_ms, 2),
        "output": output,
    }
