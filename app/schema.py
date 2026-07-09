from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TicketRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "Billing",
        "Account Access",
        "Bug Report",
        "Feature Request",
        "Integration/API",
        "General Inquiry",
        "Unclassified",
    ]
    priority: Literal["High", "Medium", "Low"]
    assigned_team: Literal[
        "Billing Ops",
        "Identity & Access",
        "Engineering",
        "Product",
        "Platform/API",
        "Customer Success",
        "Human Triage",
    ]
    reasoning: str = Field(min_length=10, max_length=280)
    confidence: float = Field(ge=0.0, le=1.0)
    sla_hours: int = Field(ge=1, le=500)
    possible_duplicate_of: Optional[str] = None

    def to_dict(self) -> dict:
        return self.model_dump()
