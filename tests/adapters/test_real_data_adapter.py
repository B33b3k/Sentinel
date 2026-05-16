"""Test for real-data adapter robustness — ensures system is ready for varied data shapes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from data.adapters.real_data_adapter import to_transaction_event
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
    """Missing fields should be filled with safe defaults."""
    raw = {}
    tx = to_transaction_event(raw)
    assert tx.account_id == "UNKNOWN"
    assert tx.amount_npr == 0.0
    assert isinstance(tx.transaction_id, uuid.UUID)

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
