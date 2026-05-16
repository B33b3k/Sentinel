"""Train one Isolation Forest per cohort, save to ml/artifacts/, log to MLflow."""
from __future__ import annotations

import pathlib
import pickle

import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score

from ml.cohorts.assign import AccountMeta, assign_cohort
from ml.training.featurize import FEATURE_COLS, featurize
from data.loader import load_accounts, load_labels, load_transactions

ARTIFACTS_DIR = pathlib.Path("ml/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def train_all(mlflow_uri: str = "http://localhost:5050") -> None:
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("isolation_forest")

    txs = load_transactions()
    accts = load_accounts()
    labels = load_labels()

    features = featurize(txs, accts)
    features = features.merge(labels[["transaction_id", "is_fraud"]], on="transaction_id", how="left")
    features["is_fraud"] = features["is_fraud"].fillna(False)

    # Assign cohort to each account
    acct_cohort = {}
    for _, row in accts.iterrows():
        meta = AccountMeta(
            account_id=row["account_id"],
            account_type=row["account_type"],
            home_district=row["home_district"],
            account_age_days=int(row["account_age_days"]),
        )
        acct_cohort[row["account_id"]] = assign_cohort(meta)

    features["cohort"] = features["account_id"].map(acct_cohort).fillna("fallback")

    for cohort, grp in features.groupby("cohort"):
        X = grp[FEATURE_COLS].values.astype(np.float32)
        y = grp["is_fraud"].values

        model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
        model.fit(X)

        # IF scores: lower = more anomalous; invert for fraud probability
        raw = model.decision_function(X)
        scores = 1 - (raw - raw.min()) / (raw.max() - raw.min() + 1e-9)

        auc = roc_auc_score(y, scores) if y.sum() > 0 else float("nan")

        path = ARTIFACTS_DIR / f"if_{cohort}.pkl"
        with open(path, "wb") as f:
            pickle.dump(model, f)

        with mlflow.start_run(run_name=f"IF_{cohort}"):
            mlflow.log_param("cohort", cohort)
            mlflow.log_param("n_samples", len(X))
            mlflow.log_metric("auc", auc)
            mlflow.log_artifact(str(path))

        print(f"  [{cohort}] n={len(X)}, AUC={auc:.3f}, saved → {path}")

    print("Isolation Forest training complete.")


if __name__ == "__main__":
    train_all()
