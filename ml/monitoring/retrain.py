"""Retraining trigger — re-runs Sprint 5 training pipeline."""
from __future__ import annotations

import subprocess
import sys


def retrain(reason: str = "manual") -> None:
    print(f"[retrain] Triggered — reason: {reason}")
    subprocess.run([sys.executable, "ml/training/train_isolation_forest.py"], check=True)
    subprocess.run([sys.executable, "ml/training/train_lstm.py"], check=True)
    print("[retrain] Complete — new models in ml/artifacts/")


if __name__ == "__main__":
    retrain(reason="cli")
