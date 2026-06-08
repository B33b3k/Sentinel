"""Build feature matrix from transactions parquet for ML training."""
from __future__ import annotations

import math
import pathlib

import numpy as np
import pandas as pd

from data.loader import DATA_DIR

# The 4 model-feature buckets. Kept at 4 (not the 8 real txn_types) so FEATURE_COLS
# / LSTM input_dim stay stable and existing trained models load without retraining.
TX_TYPES = ["P2P", "QR_ESEWA", "SWIFT_REMITTANCE", "ATM_POS"]

# Real Track-B txn_type enum (DATA_DESCRIPTION §3.1) → the 4 buckets above.
# Values already equal to a bucket name pass through unchanged.
TX_TYPE_BUCKET: dict[str, str] = {
    "ESEWA_P2P": "P2P", "MOBILE_TOPUP": "P2P", "UTILITY_BILL": "P2P",
    "KHALTI_QR": "QR_ESEWA",
    "SWIFT_OUTWARD": "SWIFT_REMITTANCE", "RTGS": "SWIFT_REMITTANCE",
    "CARD_POS": "ATM_POS", "ATM_WITHDRAWAL": "ATM_POS",
}


def bucket_txn_type(value: str) -> str:
    """Collapse a real txn_type into one of the 4 model-feature buckets."""
    return TX_TYPE_BUCKET.get(value, value)


def featurize(txs: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """Return feature DataFrame aligned with txs index."""
    df = txs.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Log-transform amount
    df["f_log_amount"] = np.log1p(df["amount_npr"])

    # Cyclical hour
    hour = df["timestamp"].dt.hour
    df["f_hour_sin"] = np.sin(2 * math.pi * hour / 24)
    df["f_hour_cos"] = np.cos(2 * math.pi * hour / 24)

    # Cyclical day-of-week
    dow = df["timestamp"].dt.dayofweek
    df["f_dow_sin"] = np.sin(2 * math.pi * dow / 7)
    df["f_dow_cos"] = np.cos(2 * math.pi * dow / 7)

    # Weekend flag
    df["f_is_weekend"] = (dow >= 5).astype(float)

    # Amount z-score vs account mean
    acct_stats = df.groupby("account_id")["amount_npr"].agg(["mean", "std"]).rename(
        columns={"mean": "_amt_mean", "std": "_amt_std"}
    )
    df = df.join(acct_stats, on="account_id")
    df["f_amount_zscore"] = (df["amount_npr"] - df["_amt_mean"]) / (df["_amt_std"].clip(lower=1))

    # Inter-tx interval (seconds) — sorted per account
    df = df.sort_values(["account_id", "timestamp"])
    df["f_inter_tx_s"] = (
        df.groupby("account_id")["timestamp"]
        .diff()
        .dt.total_seconds()
        .fillna(0)
        .clip(upper=86400)
    )

    # Merchant seen before (binary) — cumulative unique counterparties
    df["f_merchant_seen"] = (
        df.groupby("account_id")["counterparty_id"]
        .transform(lambda s: s.duplicated(keep="first").astype(float))
    )

    # Transaction type one-hot (real 8-value enum bucketed into the 4 model buckets)
    bucketed = df["transaction_type"].map(TX_TYPE_BUCKET).fillna(df["transaction_type"])
    for t in TX_TYPES:
        df[f"f_type_{t}"] = (bucketed == t).astype(float)

    feature_cols = [c for c in df.columns if c.startswith("f_")]
    return df[["transaction_id", "account_id", "timestamp"] + feature_cols].fillna(0)


FEATURE_COLS = [
    "f_log_amount", "f_hour_sin", "f_hour_cos", "f_dow_sin", "f_dow_cos",
    "f_is_weekend", "f_amount_zscore", "f_inter_tx_s", "f_merchant_seen",
    "f_type_P2P", "f_type_QR_ESEWA", "f_type_SWIFT_REMITTANCE", "f_type_ATM_POS",
]  # 13 features → input_dim=13


if __name__ == "__main__":
    from data.loader import load_accounts, load_transactions
    txs = load_transactions()
    accts = load_accounts()
    features = featurize(txs, accts)
    out = DATA_DIR / "features.parquet"
    features.to_parquet(out, index=False)
    print(f"Features saved: {features.shape}, cols: {[c for c in features.columns if c.startswith('f_')]}")
