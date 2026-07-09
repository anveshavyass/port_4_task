import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics import compute_sla_hours, find_duplicate_ticket
from app.router import route_ticket


def test_route_ticket_empty_input():
    result = route_ticket("")
    assert result["category"] == "Unclassified"
    assert result["assigned_team"] == "Human Triage"


def test_route_ticket_short_input():
    result = route_ticket("broken")
    assert result["category"] == "Unclassified"
    assert result["assigned_team"] == "Human Triage"


def test_route_ticket_includes_sla_hours():
    result = route_ticket("I need a refund for a double charge")
    assert result["category"] == "Billing"
    assert result["sla_hours"] == compute_sla_hours(result["priority"])


def test_duplicate_detection_finds_recent_match():
    history = [
        {"input": "I cannot log into my account because my password reset failed", "timestamp": "2026-01-01T00:00:00+00:00"},
    ]
    match = find_duplicate_ticket("can't log into my account", history)
    assert match is not None
    assert "account" in match["input"].lower()
