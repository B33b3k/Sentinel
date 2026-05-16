#!/bin/bash
set -e

echo "🚀 SENTINEL — Full Stack Startup"
echo "=================================="

# Check if data exists
if [ ! -f "data/seeds/transactions.parquet" ]; then
    echo "⚠️  No seed data found. Generating..."
    python3 data/generators/generate.py --accounts 5000
fi

# Check if models exist
if [ ! -f "ml/artifacts/lstm_savings_urban.pt" ]; then
    echo "⚠️  No trained models found. Training..."
    bash scripts/train_all_models.sh
fi

echo ""
echo "📦 Starting infrastructure..."
docker compose up -d zookeeper kafka redis neo4j postgres mlflow

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 20

echo ""
echo "🔧 Initializing Kafka topics..."
bash scripts/init_kafka.sh

echo ""
echo "🔧 Seeding Redis and Neo4j..."
bash scripts/seed_all.sh

echo ""
echo "🏗️  Building and starting orchestrator..."
docker compose up -d orchestrator

echo ""
echo "⏳ Waiting for orchestrator..."
sleep 10

echo ""
echo "🎨 Building and starting frontend..."
docker compose up -d frontend

echo ""
echo "✅ All services started!"
echo ""
echo "📊 Access points:"
echo "   Frontend:     http://localhost:3000"
echo "   Orchestrator: http://localhost:8000"
echo "   MLflow:       http://localhost:5050"
echo "   Neo4j:        http://localhost:7474"
echo ""
echo "🧪 Run tests:"
echo "   python3 -m pytest tests/agents/ tests/scenarios/ -v"
echo ""
echo "📈 Start transaction replay:"
echo "   python3 data/generators/replay.py"
echo ""
