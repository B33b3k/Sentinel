"""
Training data loader — the ONLY place that knows where training data lives.

To switch from synthetic to real data:
  1. Set DATA_DIR in .env to point at your real parquet directory, OR
  2. Set the DATA_SOURCE env var to "real" and implement load_real_data() below.

Expected parquet schema (same as synthetic):
  transactions.parquet — TransactionEvent fields + account_id
  accounts.parquet     — account_id, account_type, home_district, account_age_days
  labels.parquet       — transaction_id, is_fraud (bool), fraud_type (str, optional)

If your real data has a different schema, run it through the adapter first:
  from data.adapters.real_data_adapter import to_transaction_event
"""
from __future__ import annotations

import os
import pathlib

import pandas as pd

# ── Swap point ────────────────────────────────────────────────────────────────
# Change DATA_DIR env var (or edit the default below) to point at real data.
_DEFAULT_DATA_DIR = pathlib.Path("data/seeds")
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", str(_DEFAULT_DATA_DIR)))
# ─────────────────────────────────────────────────────────────────────────────


def load_transactions() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "transactions.parquet")


def load_accounts() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "accounts.parquet")


def load_labels() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "labels.parquet")
