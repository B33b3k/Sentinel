"""
Training data loader — the ONLY place that knows where training data lives.

Two sources, selected by the DATA_SOURCE env var:

  DATA_SOURCE=synthetic  (default) — reads data/seeds/*.parquet produced by
                          data.generators.generate. Internal schema already.

  DATA_SOURCE=real        — reads the GIBL Track-B files (CSV/JSON) described in
                          DATA_DESCRIPTION_Track_B.md from REAL_DATA_DIR (default
                          "structured/"), joins them per §7, and normalises column
                          names + enums to the internal TransactionEvent schema
                          using the same maps as data.adapters.real_data_adapter.

Internal schema returned by every loader function:
  transactions — TransactionEvent fields + account_id
  accounts     — account_id, account_type, home_district, account_age_days
  labels       — transaction_id, is_fraud (bool), fraud_type (str | None)
"""
from __future__ import annotations

import functools
import json
import os
import pathlib

import pandas as pd

from data.adapters.real_data_adapter import _ACCT_TYPE_MAP, _TX_TYPE_MAP

# ── Swap point ────────────────────────────────────────────────────────────────
_DEFAULT_DATA_DIR = pathlib.Path("data/seeds")
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", str(_DEFAULT_DATA_DIR)))

DATA_SOURCE = os.getenv("DATA_SOURCE", "synthetic").lower()
REAL_DATA_DIR = pathlib.Path(os.getenv("REAL_DATA_DIR", "structured"))
# Reference date used to derive account_age_days from customer_since (§3.2).
# Pinned for reproducibility; override to match the dataset snapshot if needed.
REFERENCE_DATE = pd.Timestamp(os.getenv("REFERENCE_DATE", "2026-06-08"))
# ─────────────────────────────────────────────────────────────────────────────


def load_transactions() -> pd.DataFrame:
    if DATA_SOURCE == "real":
        return _real_frames()["transactions"]
    return pd.read_parquet(DATA_DIR / "transactions.parquet")


def load_accounts() -> pd.DataFrame:
    if DATA_SOURCE == "real":
        return _real_frames()["accounts"]
    return pd.read_parquet(DATA_DIR / "accounts.parquet")


def load_labels() -> pd.DataFrame:
    if DATA_SOURCE == "real":
        return _real_frames()["labels"]
    return pd.read_parquet(DATA_DIR / "labels.parquet")


# ── Real Track-B loading ────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _real_frames() -> dict[str, pd.DataFrame]:
    """Read + join the real CSV/JSON tables into the internal schema (cached)."""
    return load_real_data(REAL_DATA_DIR)


def load_real_data(base: pathlib.Path | str = REAL_DATA_DIR) -> dict[str, pd.DataFrame]:
    """Build (transactions, accounts, labels) frames from the real Track-B files.

    Implements the join recipe in DATA_DESCRIPTION §7: transactions_raw ⋈ geo_events
    ⋈ velocity_snapshots on txn_id, ⋈ customer_profiles on account_id.
    """
    base = pathlib.Path(base)

    txn = pd.read_csv(base / "transactions_raw.csv")
    prof = pd.read_csv(base / "customer_profiles.csv")

    # geo_events (§3.4) — one row per txn; bring IP-resolved location.
    geo_path = base / "geo_events.csv"
    if geo_path.exists():
        geo = pd.read_csv(geo_path, usecols=lambda c: c in {
            "txn_id", "latitude", "longitude", "ip_city",
        })
        txn = txn.merge(geo, on="txn_id", how="left")

    # velocity_snapshots (§3.5) — pre-computed sliding-window features; kept as
    # extra columns (drop the duplicated account_id/snapshot_time join keys).
    vel_path = base / "velocity_snapshots.csv"
    if vel_path.exists():
        vel = pd.read_csv(vel_path).drop(columns=["account_id", "snapshot_time"], errors="ignore")
        txn = txn.merge(vel, on="txn_id", how="left")

    # customer_profiles (§3.2) — derive internal account fields.
    prof = prof.copy()
    prof["customer_since"] = pd.to_datetime(prof["customer_since"], errors="coerce")
    prof["account_age_days"] = (REFERENCE_DATE - prof["customer_since"]).dt.days.clip(lower=0).fillna(0).astype(int)
    prof["account_type"] = prof["occupation_category"].map(_ACCT_TYPE_MAP).fillna("SAVINGS")

    accounts = prof.rename(columns={"district": "home_district"})[
        ["account_id", "account_type", "home_district", "account_age_days"]
    ].copy()

    txn = txn.merge(
        prof[["account_id", "account_age_days", "account_type", "district"]],
        on="account_id", how="left",
    )

    # Normalise transaction columns to the internal schema.
    txn = txn.rename(columns={
        "txn_id": "transaction_id",
        "txn_type": "transaction_type",
        "latitude": "geo_lat",
        "longitude": "geo_lon",
        "ip_city": "geo_city",
        "district": "account_home_district",
    })
    txn["transaction_type"] = txn["transaction_type"].map(
        lambda v: _TX_TYPE_MAP.get(v, v)
    )
    txn["geo_district"] = txn.get("geo_city")
    txn["account_age_days"] = txn["account_age_days"].fillna(0).astype(int)
    txn["account_type"] = txn["account_type"].fillna("SAVINGS")

    # Labels (§3.9) — only the released training split.
    labels = pd.read_csv(base / "fraud_labels_train.csv").rename(
        columns={"txn_id": "transaction_id"}
    )
    label_cols = [c for c in ("transaction_id", "is_fraud", "fraud_type") if c in labels.columns]
    labels = labels[label_cols]

    return {"transactions": txn, "accounts": accounts, "labels": labels}


def load_device_fingerprints(base: pathlib.Path | str = REAL_DATA_DIR) -> pd.DataFrame:
    """Load device_fingerprints.json (§3.3) as a DataFrame."""
    base = pathlib.Path(base)
    with open(base / "device_fingerprints.json") as f:
        return pd.DataFrame(json.load(f))
