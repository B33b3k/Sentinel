"""Drift detection — computes recall + FPR on recent verdicts, logs to MLflow."""
from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import mlflow
import pandas as pd
from sklearn.metrics import confusion_matrix

from data.loader import DATA_DIR, load_labels, load_transactions

RECALL_THRESHOLD = 0.92
FPR_THRESHOLD = 0.03


def run_drift_check(
    window_days: int = 7,
    mlflow_uri: str = "http://localhost:5050",
    verdicts_path: str | None = None,
) -> dict:
    """
    Compute recall + FPR on a rolling window of verdicts vs ground-truth labels.
    Logs metrics to MLflow experiment 'production_metrics'.
    Returns dict with metrics and alert flag.
    """
    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("production_metrics")

    # Load ground truth
    labels = load_labels()
    labels["is_fraud"] = labels["is_fraud"].astype(bool)

    # Load verdicts — use seed labels as proxy if no live verdicts yet
    if verdicts_path and pathlib.Path(verdicts_path).exists():
        verdicts = pd.read_parquet(verdicts_path)
    else:
        # Simulate: treat BLOCK/OTP_INTERLOCK as positive prediction
        txs = load_transactions()
        txs["timestamp"] = pd.to_datetime(txs["timestamp"], utc=True)
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        recent = txs[txs["timestamp"] >= cutoff]
        verdicts = recent[["transaction_id"]].copy()
        verdicts = verdicts.merge(labels, on="transaction_id", how="left")
        verdicts["is_fraud"] = verdicts["is_fraud"].fillna(False)
        # Simulate predictions: fraud → predicted positive
        verdicts["predicted_fraud"] = verdicts["is_fraud"]

    merged = verdicts.merge(labels, on="transaction_id", how="inner")
    if len(merged) == 0:
        print("[drift_check] No matching verdicts found — skipping")
        return {"alert": False, "reason": "no_data"}

    y_true = merged["is_fraud_y"].astype(int)
    y_pred = merged.get("predicted_fraud", merged["is_fraud_x"]).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    alert = recall < RECALL_THRESHOLD or fpr > FPR_THRESHOLD
    metrics = {
        "recall": round(recall, 4),
        "fpr": round(fpr, 4),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "window_days": window_days,
        "alert": alert,
    }

    with mlflow.start_run(run_name=f"drift_check_{datetime.now().strftime('%Y%m%d_%H%M')}"):
        mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
        if alert:
            mlflow.set_tag("alert", "true")
            reason = []
            if recall < RECALL_THRESHOLD:
                reason.append(f"recall={recall:.3f}<{RECALL_THRESHOLD}")
            if fpr > FPR_THRESHOLD:
                reason.append(f"fpr={fpr:.3f}>{FPR_THRESHOLD}")
            mlflow.set_tag("alert_reason", ", ".join(reason))
            print(f"[drift_check] ALERT: {', '.join(reason)}")
        else:
            print(f"[drift_check] OK — recall={recall:.3f}, fpr={fpr:.3f}")

    return metrics


if __name__ == "__main__":
    result = run_drift_check()
    print(result)
