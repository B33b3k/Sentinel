"""
Real-data adapter — UPDATE THIS FILE when the actual data format is confirmed.

This is the ONLY place that knows about the real payload structure.
Everything else in SENTINEL consumes TransactionEvent.

Usage:
    from data.adapters.real_data_adapter import to_transaction_event
    tx = to_transaction_event(raw_dict)

When the real format arrives:
    1. Fill in _map_fields() with the actual field mappings.
    2. Update _parse_transaction_type() and _parse_account_type() if enums differ.
    3. Run: pytest tests/adapters/ -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from orchestrator.schemas import TransactionEvent

# ---------------------------------------------------------------------------
# ⚠️  PLACEHOLDER MAPPINGS — replace with real field names when known
# ---------------------------------------------------------------------------
_FIELD_MAP: dict[str, str] = {
    # "real_field_name": "TransactionEvent_field_name"
    # e.g. "txn_id": "transaction_id",
    #      "acct_no": "account_id",
    #      "txn_amount": "amount_npr",
}

_TX_TYPE_MAP: dict[str, str] = {
    # "REAL_TYPE": "P2P" | "QR_ESEWA" | "SWIFT_REMITTANCE" | "ATM_POS" | ...
    # e.g. "TRANSFER": "P2P",
}

_ACCT_TYPE_MAP: dict[str, str] = {
    # "REAL_ACCT_TYPE": "SAVINGS" | "CURRENT" | "SALARY" | "REMITTANCE" | ...
}
# ---------------------------------------------------------------------------


def to_transaction_event(raw: dict[str, Any]) -> TransactionEvent:
    """Normalise a raw payload into TransactionEvent.

    Falls back gracefully for any missing field so the system keeps running
    even before the real format is confirmed.
    """
    mapped = _map_fields(raw)
    return TransactionEvent(
        transaction_id=_get(mapped, "transaction_id", str(uuid.uuid4())),
        account_id=_get(mapped, "account_id", "UNKNOWN"),
        timestamp=_parse_ts(_get(mapped, "timestamp", None)),
        amount_npr=float(_get(mapped, "amount_npr", 0.0)),
        currency=_get(mapped, "currency", "NPR"),
        transaction_type=_parse_transaction_type(_get(mapped, "transaction_type", "")),
        counterparty_id=_get(mapped, "counterparty_id", None),
        counterparty_name=_get(mapped, "counterparty_name", None),
        device_id=_get(mapped, "device_id", "unknown"),
        ip_address=_get(mapped, "ip_address", "0.0.0.0"),
        geo_lat=float(_get(mapped, "geo_lat", 0.0)),
        geo_lon=float(_get(mapped, "geo_lon", 0.0)),
        geo_city=_get(mapped, "geo_city", "unknown"),
        geo_district=_get(mapped, "geo_district", "unknown"),
        account_age_days=int(_get(mapped, "account_age_days", 0)),
        account_home_district=_get(mapped, "account_home_district", "unknown"),
        account_type=_parse_account_type(_get(mapped, "account_type", "")),
    )


def from_synthetic(row: dict[str, Any]) -> TransactionEvent:
    """Convert a row from our synthetic parquet directly (no remapping needed)."""
    return TransactionEvent(**{k: v for k, v in row.items() if k not in ("is_fraud", "fraud_type")})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _map_fields(raw: dict[str, Any]) -> dict[str, Any]:
    if not _FIELD_MAP:
        return raw  # no mapping defined yet — pass through as-is
    return {_FIELD_MAP.get(k, k): v for k, v in raw.items()}


def _get(d: dict, key: str, default: Any) -> Any:
    v = d.get(key)
    return v if v is not None else default


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _parse_transaction_type(raw: str) -> str:
    return _TX_TYPE_MAP.get(raw, raw) if raw else "UNKNOWN"


def _parse_account_type(raw: str) -> str:
    return _ACCT_TYPE_MAP.get(raw, raw) if raw else "UNKNOWN"
