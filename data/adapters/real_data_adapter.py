"""
Real-data adapter — mapped to the GIBL Track-B data spec (DATA_DESCRIPTION_Track_B.md).

This is the ONLY place that knows about the real payload structure.
Everything else in SENTINEL consumes TransactionEvent.

Usage:
    from data.adapters.real_data_adapter import to_transaction_event
    tx = to_transaction_event(raw_dict)

The raw dict is one row of `transactions_raw` (DATA_DESCRIPTION §3.1), optionally
already merged with `geo_events` (§3.4), `velocity_snapshots` (§3.5) and
`customer_profiles` (§3.2) columns — `data.loader.load_real_data()` produces that
merged record. Any field absent in the raw payload falls back to a safe default.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from orchestrator.schemas import TransactionEvent

# Nepal Standard Time — DATA_DESCRIPTION §3.1/§7: timestamps are UTC+5:45.
# Naive timestamps (the real CSV format `YYYY-MM-DD HH:MM:SS.mmm`) are NPT-local;
# normalising here keeps `night_flag` / hour-of-day signals correct downstream.
NPT = timezone(timedelta(hours=5, minutes=45))

# ---------------------------------------------------------------------------
# Field mappings — real Track-B column names → TransactionEvent attributes.
# Columns whose names already match (account_id, timestamp, amount_npr, currency,
# counterparty_id, device_id, ip_address, account_age_days) need no entry.
# ---------------------------------------------------------------------------
_FIELD_MAP: dict[str, str] = {
    "txn_id": "transaction_id",            # §3.1 TXN-YYYYMMDD-XXXXXXXX
    "txn_type": "transaction_type",        # §3.1 8-value enum (see _CANONICAL_TXN_TYPES)
    # geo_events (§3.4) — joined on txn_id by load_real_data()
    "latitude": "geo_lat",
    "longitude": "geo_lon",
    "ip_city": "geo_city",
    # customer_profiles (§3.2) — joined on account_id
    "district": "account_home_district",
    "occupation_category": "account_type",  # translated via _ACCT_TYPE_MAP
}

# §3.1 canonical txn_type values — adopted as SENTINEL's internal vocabulary.
_CANONICAL_TXN_TYPES = frozenset({
    "ESEWA_P2P", "CARD_POS", "ATM_WITHDRAWAL", "SWIFT_OUTWARD",
    "KHALTI_QR", "RTGS", "MOBILE_TOPUP", "UTILITY_BILL",
})

# Real types pass through unchanged; this map only normalises legacy aliases.
_TX_TYPE_MAP: dict[str, str] = {
    "P2P": "ESEWA_P2P",
    "QR_ESEWA": "KHALTI_QR",
    "SWIFT_REMITTANCE": "SWIFT_OUTWARD",
    "ATM_POS": "CARD_POS",
}

# customer_profiles has no account_type; derive it from occupation_category (§3.2)
# so the existing cohort scheme (SAVINGS/CURRENT/SALARY/REMITTANCE) keeps working.
_ACCT_TYPE_MAP: dict[str, str] = {
    "SALARIED": "SALARY",
    "GOVERNMENT": "SALARY",
    "BUSINESS_OWNER": "CURRENT",
    "SELF_EMPLOYED": "CURRENT",
    "REMITTANCE_DEPENDENT": "REMITTANCE",
    "STUDENT": "SAVINGS",
}
# ---------------------------------------------------------------------------


def to_transaction_event(raw: dict[str, Any]) -> TransactionEvent:
    """Normalise a raw payload into TransactionEvent.

    Falls back gracefully for any missing field so the system keeps running
    even before the real format is confirmed.
    """
    mapped = _map_fields(raw)
    
    # Identify fields that are already mapped to TransactionEvent attributes
    known_fields = {
        "transaction_id", "account_id", "timestamp", "amount_npr", "currency",
        "transaction_type", "counterparty_id", "counterparty_name",
        "device_id", "ip_address", "geo_lat", "geo_lon", "geo_city", "geo_district",
        "account_age_days", "account_home_district", "account_type"
    }
    
    return TransactionEvent(
        transaction_id=_get(mapped, "transaction_id", str(uuid.uuid4())),
        account_id=_get(mapped, "account_id", "UNKNOWN"),
        timestamp=_parse_ts(_get(mapped, "timestamp", None)),
        amount_npr=_to_float(_get(mapped, "amount_npr", 0.0)),
        currency=_get(mapped, "currency", "NPR"),
        transaction_type=_parse_transaction_type(_get(mapped, "transaction_type", "")),
        counterparty_id=_get(mapped, "counterparty_id", None),
        counterparty_name=_get(mapped, "counterparty_name", None),
        device_id=_get(mapped, "device_id", "unknown"),
        ip_address=_get(mapped, "ip_address", "0.0.0.0"),
        geo_lat=_to_float(_get(mapped, "geo_lat", 0.0)),
        geo_lon=_to_float(_get(mapped, "geo_lon", 0.0)),
        geo_city=_get(mapped, "geo_city", "unknown"),
        geo_district=_get(mapped, "geo_district", "unknown"),
        account_age_days=_to_int(_get(mapped, "account_age_days", 0)),
        account_home_district=_get(mapped, "account_home_district", "unknown"),
        account_type=_parse_account_type(_get(mapped, "account_type", "")),
        extra={k: v for k, v in raw.items() if k not in known_fields and k not in _FIELD_MAP}
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
    # Naive datetimes are treated as NPT (DATA_DESCRIPTION §3.1/§7); tz-aware
    # values (ISO with Z/offset, e.g. JSON datetimes) keep their own zone.
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=NPT)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=NPT)
        except ValueError:
            pass
    return datetime.now(NPT)


def _parse_transaction_type(raw: str) -> str:
    return _TX_TYPE_MAP.get(raw, raw) if raw else "UNKNOWN"


def _parse_account_type(raw: str) -> str:
    return _ACCT_TYPE_MAP.get(raw, raw) if raw else "UNKNOWN"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
