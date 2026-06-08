"""featurize() timezone handling: naive timestamps are NPT (DATA_DESCRIPTION §3.1/§7)."""
from __future__ import annotations

import pandas as pd

from ml.training.featurize import featurize


def _accounts() -> pd.DataFrame:
    return pd.DataFrame([
        {"account_id": "ACC-0000001", "account_type": "SAVINGS",
         "home_district": "Kathmandu", "account_age_days": 400},
    ])


def test_naive_timestamp_treated_as_npt():
    # 02:14 NPT must stay hour=2 (night) — not be shifted to UTC (20:29 prev day).
    txs = pd.DataFrame([
        {"transaction_id": "TXN-1", "account_id": "ACC-0000001",
         "timestamp": "2026-05-31 02:14:07.481", "amount_npr": 85000.0,
         "transaction_type": "ESEWA_P2P", "counterparty_id": "ACC-0000002"},
    ])
    feats = featurize(txs, _accounts())
    # hour=2 → sin(2π·2/24) ≈ 0.5, cos ≈ 0.866; the UTC misreading (hour=20)
    # would give a negative sine, so this pins the NPT interpretation.
    assert feats.loc[0, "f_hour_sin"] > 0
    assert feats.loc[0, "f_hour_cos"] > 0
