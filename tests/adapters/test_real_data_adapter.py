"""Test for real-data adapter robustness — ensures system is ready for varied data shapes."""
from __future__ import annotations

import uuid

from data.adapters.real_data_adapter import NPT, to_transaction_event
from orchestrator.schemas import TransactionEvent

def test_adapter_minimal_payload():
    """Minimal payload should result in a valid TransactionEvent with defaults."""
    raw = {"transaction_id": str(uuid.uuid4()), "account_id": "ACC_001", "amount_npr": 5000}
    tx = to_transaction_event(raw)
    assert isinstance(tx, TransactionEvent)
    assert tx.account_id == "ACC_001"
    assert tx.amount_npr == 5000.0
    assert tx.transaction_type == "UNKNOWN"
    assert tx.device_id == "unknown"

def test_adapter_missing_fields():
    """Missing fields should be filled with safe defaults; txn_id is a string."""
    raw = {}
    tx = to_transaction_event(raw)
    assert tx.account_id == "UNKNOWN"
    assert tx.amount_npr == 0.0
    assert isinstance(tx.transaction_id, str)


def test_adapter_real_txn_id_string():
    """Real Track-B txn_id (TXN-YYYYMMDD-XXXXXXXX) must survive unchanged."""
    raw = {"txn_id": "TXN-20260531-A9F3C1AB", "account_id": "ACC-0048293", "amount_npr": 85000}
    tx = to_transaction_event(raw)
    assert tx.transaction_id == "TXN-20260531-A9F3C1AB"
    assert tx.account_id == "ACC-0048293"


def test_adapter_maps_real_columns():
    """Real column names + enums map to the internal schema (DATA_DESCRIPTION §3)."""
    raw = {
        "txn_id": "TXN-20260531-DEADBEEF",
        "txn_type": "ESEWA_P2P",
        "occupation_category": "REMITTANCE_DEPENDENT",
        "latitude": 27.7,
        "longitude": 85.3,
        "ip_city": "Kathmandu",
        "district": "Pokhara",
    }
    tx = to_transaction_event(raw)
    assert tx.transaction_type == "ESEWA_P2P"      # real enum passes through
    assert tx.account_type == "REMITTANCE"          # occupation → account_type
    assert tx.geo_lat == 27.7 and tx.geo_lon == 85.3
    assert tx.geo_city == "Kathmandu"
    assert tx.account_home_district == "Pokhara"


def test_adapter_legacy_txn_type_alias():
    """Legacy synthetic txn_type values normalise to the real enum."""
    tx = to_transaction_event({"txn_type": "SWIFT_REMITTANCE"})
    assert tx.transaction_type == "SWIFT_OUTWARD"


def test_adapter_naive_timestamp_is_npt():
    """Naive timestamps are interpreted as Nepal Standard Time (§3.1/§7)."""
    tx = to_transaction_event({"timestamp": "2026-05-31 02:14:07.481"})
    assert tx.timestamp.utcoffset() == NPT.utcoffset(None)
    assert tx.timestamp.hour == 2  # NPT-local hour preserved for night_flag

def test_adapter_varied_timestamp_formats():
    """Should handle ISO, timestamp, and datetime objects."""
    iso_ts = "2026-05-15T21:30:00Z"
    tx1 = to_transaction_event({"timestamp": iso_ts})
    assert tx1.timestamp.year == 2026
    
    unix_ts = 1778967000.0  # roughly 2026
    tx2 = to_transaction_event({"timestamp": unix_ts})
    assert tx2.timestamp.year == 2026

def test_adapter_preserves_extra_fields():
    """Extra fields should be preserved in the 'extra' dict."""
    raw = {"account_id": "A1", "unknown_field": "secret_value"}
    tx = to_transaction_event(raw)
    assert tx.extra["unknown_field"] == "secret_value"

def test_adapter_invalid_types_graceful_fail():
    """Invalid types for numeric fields should fallback to 0.0 instead of crashing."""
    raw = {"amount_npr": "not_a_number"}
    tx = to_transaction_event(raw)
    assert tx.amount_npr == 0.0
