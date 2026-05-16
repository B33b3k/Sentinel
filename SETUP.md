# SENTINEL — Full Setup Guide

## Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local data generation and model training)
- Node.js 20+ (only if running frontend locally)

## Complete Docker Setup (Recommended)

### 1. Initial Setup (One-time)

```bash
# Clone repository
git clone <repo>
cd sentinel

# Generate synthetic data (100K transactions, 5K accounts)
python3 data/generators/generate.py --accounts 5000

# Train all ML models (LSTM + Isolation Forest per cohort)
bash scripts/train_all_models.sh
```

This creates:
- `data/seeds/accounts.parquet` (5,000 accounts)
- `data/seeds/transactions.parquet` (~100K transactions)
- `data/seeds/labels.parquet` (fraud ground truth)
- `ml/artifacts/*.pt` (6 LSTM models)
- `ml/artifacts/*.pkl` (6 Isolation Forest models)

### 2. Start Full Stack

```bash
# Start all services (infrastructure + orchestrator + frontend)
bash scripts/start_all.sh
```

This will:
1. Start Kafka, Redis, Neo4j, Postgres, MLflow
2. Initialize Kafka topics
3. Seed Redis with velocity baselines
4. Load Neo4j graph
5. Build and start orchestrator
6. Build and start frontend

### 3. Access Services

| Service      | URL                          | Credentials         |
|--------------|------------------------------|---------------------|
| Dashboard    | http://localhost:3000        | -                   |
| Orchestrator | http://localhost:8000        | -                   |
| MLflow       | http://localhost:5050        | -                   |
| Neo4j        | http://localhost:7474        | neo4j/sentinelpass  |

### 4. Run Demo Scenarios

```bash
# Run all scenario tests
python3 -m pytest tests/scenarios/ -v

# Or trigger from dashboard
# Click scenario buttons in the UI
```

### 5. Start Live Transaction Stream

```bash
# Replay transactions at 1000 TPS
python3 data/generators/replay.py

# Watch verdicts appear in dashboard in real-time
```

### 6. Run Load Test

```bash
# Install locust if not already
pip install locust

# Run 500 concurrent users for 60s
locust -f tests/load/locustfile.py --headless -u 500 -r 100 -t 60s --host http://localhost:8000
```

## Service Management

```bash
# View logs
docker compose logs -f orchestrator
docker compose logs -f frontend

# Restart a service
docker compose restart orchestrator

# Stop all services
docker compose down

# Stop and remove all data
docker compose down -v

# Rebuild after code changes
docker compose up -d --build orchestrator
docker compose up -d --build frontend
```

## Development Workflow

### Local Orchestrator + Dockerized Infrastructure

```bash
# Start only infrastructure
docker compose up -d zookeeper kafka redis neo4j postgres mlflow

# Run orchestrator locally
poetry install
poetry run uvicorn orchestrator.main:app --reload --port 8000

# Run frontend locally
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# All tests
python3 -m pytest tests/ -v

# Agent tests only
python3 -m pytest tests/agents/ -v

# Scenario tests only
python3 -m pytest tests/scenarios/ -v

# Specific test
python3 -m pytest tests/scenarios/sita.py -v
```

## Troubleshooting

### Services not healthy

```bash
# Check service status
docker compose ps

# Check logs
docker compose logs <service-name>

# Common fixes
docker compose down
docker compose up -d
```

### Kafka topics missing

```bash
bash scripts/init_kafka.sh
```

### Redis empty

```bash
bash scripts/seed_all.sh
```

### Models not found

```bash
bash scripts/train_all_models.sh
```

### Frontend can't connect to orchestrator

Check `frontend/src/App.tsx` — API URL should be `http://localhost:8000` for local dev or proxied via nginx in Docker.

### Port conflicts

Edit `docker-compose.yml` to change port mappings:
```yaml
ports:
  - "3001:80"  # Change 3000 to 3001
```

## Architecture

```
┌─────────────┐
│  Frontend   │ :3000
│  (React)    │
└──────┬──────┘
       │ WebSocket + REST
┌──────▼──────────┐
│  Orchestrator   │ :8000
│  (FastAPI)      │
└─────────────────┘
       │
   ┌───┴────┬────────┬────────┬──────────┐
   ▼        ▼        ▼        ▼          ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌────────┐
│Kafka │ │Redis │ │Neo4j │ │Postgres│ │MLflow  │
│:9092 │ │:6379 │ │:7687 │ │:5432   │ │:5050   │
└──────┘ └──────┘ └──────┘ └────────┘ └────────┘
```

## Performance Targets

- **Latency:** P99 < 380ms (target: < 800ms)
- **Throughput:** 10,000 TPS
- **Fraud Recall:** > 97%
- **False Positive Rate:** < 2%

## Next Steps

1. ✅ Run `bash scripts/start_all.sh`
2. ✅ Open http://localhost:3000
3. ✅ Click "Sita Attack" scenario button
4. ✅ Watch the fraud detection in action
5. ✅ Start transaction replay for live stream
6. ✅ Run load tests to verify performance

---

Built for Global IME AI/ML Hackathon 2026 · Track B — Security & Fraud
