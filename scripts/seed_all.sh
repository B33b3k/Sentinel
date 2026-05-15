#!/usr/bin/env bash
set -euo pipefail

echo "=== SENTINEL seed pipeline ==="

# 1. Generate synthetic data
echo "[1/4] Generating synthetic data..."
python3 data/generators/generate.py --accounts 5000

# 2. Build velocity baselines in Redis
echo "[2/4] Loading velocity baselines into Redis..."
python3 ml/training/build_velocity_baselines.py

# 3. Seed geo history in Redis
echo "[3/4] Seeding geo history into Redis..."
python3 scripts/seed_geo_history.py

# 4. Init Kafka topics
echo "[4/4] Creating Kafka topics..."
bash scripts/init_kafka.sh

echo "=== Seed complete ==="
