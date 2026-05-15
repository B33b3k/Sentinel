"""
SENTINEL internal schemas.

⚠️  PROVISIONAL — real data format not yet confirmed.
    Field names, types, and enums below are best-guess placeholders.
    When the real data spec arrives, update the adapter in
    data/adapters/real_data_adapter.py — do NOT change these models
    directly until the team agrees on the final contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionEvent(BaseModel):
    """Working model for a transaction flowing through SENTINEL.

    All fields are provisional. The real-data adapter normalises
    incoming records into this shape before any agent sees them.
    """

    transaction_id: UUID
    account_id: str
    timestamp: datetime
    amount_npr: float
    currency: str = "NPR"
    # Provisional enum — real types may differ
    transaction_type: str = "UNKNOWN"
    counterparty_id: str | None = None
    counterparty_name: str | None = None

    device_id: str = "unknown"
    ip_address: str = "0.0.0.0"
    geo_lat: float = 0.0
    geo_lon: float = 0.0
    geo_city: str = "unknown"
    geo_district: str = "unknown"

    account_age_days: int = 0
    account_home_district: str = "unknown"
    # Provisional enum — real types may differ
    account_type: str = "UNKNOWN"

    # Catch-all for any extra fields in the real payload
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AgentScore(BaseModel):
    agent: str  # "velocity" | "geo" | "behavior" | "gnn"
    score: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str]
    latency_ms: float


class SynthesisVerdict(BaseModel):
    transaction_id: UUID
    composite_score: float = Field(ge=0.0, le=1.0)
    verdict: str  # "ALLOW" | "OTP_INTERLOCK" | "BLOCK"
    agent_scores: list[AgentScore]
    weights_used: dict[str, float]
    transaction_type: str
    total_latency_ms: float
