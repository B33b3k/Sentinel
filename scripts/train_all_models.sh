#!/usr/bin/env bash
set -euo pipefail

echo "=== SENTINEL model training ==="

echo "[1/2] Training Isolation Forest (per cohort)..."
python3 ml/training/train_isolation_forest.py

echo "[2/2] Training Behavior LSTM (per cohort)..."
python3 ml/training/train_lstm.py

echo "=== Training complete. Artifacts in ml/artifacts/ ==="
