"""Orchestrate full synthetic dataset generation → data/seeds/*.parquet"""
from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from data.generators.generate_accounts import generate_accounts
from data.generators.generate_fraud import generate_fraud
from data.generators.generate_legitimate import generate_legitimate

SEEDS_DIR = pathlib.Path("data/seeds")


def main(n_accounts: int = 5000, seed: int = 42) -> None:
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Generating {n_accounts} accounts...")
    accounts = generate_accounts(n=n_accounts, seed=seed)
    accounts.to_parquet(SEEDS_DIR / "accounts.parquet", index=False)
    print(f"  → {len(accounts)} accounts saved")

    print("Generating legitimate transactions...")
    legit = generate_legitimate(accounts, seed=seed)
    # Cap to keep total near 100K
    if len(legit) > 95000:
        legit = legit.sample(n=95000, random_state=seed).reset_index(drop=True)
    print(f"  → {len(legit)} legitimate transactions")

    print("Generating fraud transactions...")
    fraud = generate_fraud(accounts, total_legit=len(legit), seed=seed)
    print(f"  → {len(fraud)} fraud transactions")

    # Combine and shuffle
    txs = pd.concat([legit, fraud], ignore_index=True)
    txs = txs.sample(frac=1, random_state=seed).reset_index(drop=True)

    fraud_rate = txs["is_fraud"].mean()
    print(f"  → {len(txs)} total transactions, fraud rate = {fraud_rate:.2%}")
    assert 0.015 <= fraud_rate <= 0.025, f"Fraud rate {fraud_rate:.2%} out of target 1.5%-2.5%"

    # Save transactions (without label columns)
    tx_cols = [c for c in txs.columns if c not in ("is_fraud", "fraud_type")]
    txs[tx_cols].to_parquet(SEEDS_DIR / "transactions.parquet", index=False)

    # Save labels
    txs[["transaction_id", "is_fraud", "fraud_type"]].to_parquet(
        SEEDS_DIR / "labels.parquet", index=False
    )
    print(f"Saved to {SEEDS_DIR}/")
    print(txs["fraud_type"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(n_accounts=args.accounts, seed=args.seed)
