from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionEvent(BaseModel):
    transaction_id: UUID
    account_id: str
    timestamp: datetime
    amount_npr: float
    currency: str = "NPR"
    transaction_type: Literal["P2P", "QR_ESEWA", "SWIFT_REMITTANCE", "ATM_POS"]
    counterparty_id: str | None
    counterparty_name: str | None

    device_id: str
    ip_address: str
    geo_lat: float
    geo_lon: float
    geo_city: str
    geo_district: str

    account_age_days: int
    account_home_district: str
    account_type: Literal["SAVINGS", "CURRENT", "SALARY", "REMITTANCE"]


class AgentScore(BaseModel):
    agent: Literal["velocity", "geo", "behavior", "gnn"]
    score: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str]
    latency_ms: float


class SynthesisVerdict(BaseModel):
    transaction_id: UUID
    composite_score: float = Field(ge=0.0, le=1.0)
    verdict: Literal["ALLOW", "OTP_INTERLOCK", "BLOCK"]
    agent_scores: list[AgentScore]
    weights_used: dict[str, float]
    transaction_type: str
    total_latency_ms: float
