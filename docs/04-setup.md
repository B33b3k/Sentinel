# 04 - Setup Guide

## 🚀 Complete Setup Instructions

### Prerequisites

**Required:**
- Docker & Docker Compose (for infrastructure)
- Python 3.11+ (for data generation & model training)
- Node.js 20+ (for frontend, optional if using Docker)

**Optional:**
- Poetry (Python package manager)
- Git (version control)

---

## 📦 Installation Methods

### Method 1: Quick Start (Recommended)

```bash
# 1. Clone repository
git clone <repo-url>
cd sentinel

# 2. Generate synthetic data (one-time)
python3 data/generators/generate.py --accounts 5000

# 3. Train ML models (one-time)
bash scripts/train_all_models.sh

# 4. Start everything
bash scripts/start_all.sh

# 5. Open dashboard
open http://localhost:5173
```

**Time:** ~10 minutes first time, ~2 minutes subsequent starts

---

### Method 2: Step-by-Step

#### Step 1: Infrastructure Setup

```bash
# Start all infrastructure services
docker compose up -d zookeeper kafka redis neo4j postgres mlflow

# Verify all services healthy
docker compose ps

# Expected output:
# sentinel-kafka      Up (healthy)
# sentinel-redis      Up (healthy)
# sentinel-neo4j      Up (healthy)
# sentinel-postgres   Up (healthy)
# sentinel-mlflow     Up (healthy)
# sentinel-zookeeper  Up (healthy)
```

**Why this order?**
- Zookeeper must start before Kafka
- Other services can start in parallel
- Health checks ensure readiness

---

#### Step 2: Initialize Kafka Topics

```bash
bash scripts/init_kafka.sh
```

**Creates 4 topics:**
```
sentinel.transactions  (3 partitions)
sentinel.verdicts      (3 partitions)
sentinel.otp_events    (1 partition)
sentinel.retraining    (1 partition)
```

**Why 3 partitions?**
- Allows 3 parallel consumers
- Balanced load distribution
- Scales to 9K+ TPS

---

#### Step 3: Generate Synthetic Data

```bash
python3 data/generators/generate.py --accounts 5000
```

**Generates:**
- `data/seeds/accounts.parquet` (5,000 accounts)
- `data/seeds/transactions.parquet` (~100K transactions)
- `data/seeds/labels.parquet` (fraud ground truth)

**Time:** ~30 seconds

**Why synthetic data?**
- Real data format unknown until hackathon
- Allows complete system development
- Adapter pattern enables quick swap

---

#### Step 4: Train ML Models

```bash
bash scripts/train_all_models.sh
```

**Trains:**
- 6 LSTM models (one per cohort)
- 6 Isolation Forest models (one per cohort)
- Logs all experiments to MLflow

**Time:** ~5 minutes

**Output:**
```
ml/artifacts/lstm_savings_urban.pt
ml/artifacts/lstm_savings_rural.pt
ml/artifacts/lstm_salary_kathmandu.pt
ml/artifacts/lstm_salary_other.pt
ml/artifacts/lstm_overseas_worker_remittance.pt
ml/artifacts/lstm_current_business.pt
ml/artifacts/if_savings_urban.pkl
ml/artifacts/if_savings_rural.pkl
... (6 more IF models)
```

---

#### Step 5: Seed Databases

```bash
# Seed Redis with velocity baselines
python3 ml/training/build_velocity_baselines.py

# Seed Redis with geo history
python3 scripts/seed_geo_history.py

# (Optional) Load Neo4j graph
python3 graph/load_data.py
```

**Time:** ~1 minute

**What gets seeded:**
- Redis: Historical transaction counts per account
- Redis: Historical average amounts
- Redis: Known devices and locations
- Neo4j: Account nodes and transfer edges (optional)

---

#### Step 6: Start Orchestrator

```bash
# Option A: Direct (for development)
python3 -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000

# Option B: Background
nohup python3 -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000 > orchestrator.log 2>&1 &

# Option C: Docker (production)
docker compose up -d orchestrator
```

**Verify:**
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

---

#### Step 7: Start Frontend

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Option A: Development server
npm run dev
# Opens at http://localhost:5173

# Option B: Production build
npm run build
npm run preview

# Option C: Docker
docker compose up -d frontend
# Opens at http://localhost:3000
```

---

#### Step 8: Start Transaction Replay (Optional)

```bash
# Streams transactions from parquet to Kafka
python3 data/generators/replay.py

# Options:
python3 data/generators/replay.py --tps 1000  # Custom TPS
python3 data/generators/replay.py --loop      # Infinite loop
```

**What it does:**
- Reads transactions from parquet
- Publishes to Kafka at specified TPS
- Shows live processing in dashboard

---

## 🔧 Configuration

### Environment Variables

Create `.env` file:

```bash
# Infrastructure
REDIS_HOST=localhost
REDIS_PORT=6379
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=sentinelpass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=sentinel
POSTGRES_PASSWORD=sentinel
POSTGRES_DB=sentinel_audit

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_ENABLED=true

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5050

# OTP (mock for demo)
OTP_PROVIDER=mock
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### Frontend Environment

Create `frontend/.env`:

```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/verdicts
```

---

## 🐳 Docker Deployment

### Full Stack with Docker

```bash
# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f orchestrator
docker compose logs -f frontend

# Stop all
docker compose down

# Reset everything (including data)
docker compose down -v
```

### Individual Service Management

```bash
# Restart orchestrator
docker compose restart orchestrator

# Rebuild frontend
docker compose up -d --build frontend

# View service status
docker compose ps

# Execute command in container
docker compose exec orchestrator python -c "print('Hello')"
```

---

## 🧪 Verification

### Test Infrastructure

```bash
# Run smoke tests
python3 -m pytest tests/smoke/ -v

# Expected: All services reachable
```

### Test Agents

```bash
# Run agent unit tests
python3 -m pytest tests/agents/ -v

# Expected: 59/59 passing
```

### Test Scenarios

```bash
# Run scenario tests
python3 -m pytest tests/scenarios/ -v

# Expected: All 5 scenarios pass
```

### Test End-to-End

```bash
# 1. Start everything
bash scripts/start_all.sh

# 2. Trigger scenario via API
curl -X POST http://localhost:8000/scenarios/run/sita

# 3. Check verdict
# Expected: {"verdict":"BLOCK","composite_score":0.855,...}

# 4. Check dashboard
open http://localhost:5173
# Expected: Transaction appears in stream
```

---

## 🔍 Troubleshooting

### Services Won't Start

**Problem:** Docker services unhealthy

**Solution:**
```bash
# Check logs
docker compose logs kafka
docker compose logs redis

# Common fixes:
docker compose down -v  # Remove volumes
docker compose up -d    # Restart
```

---

### Kafka Topics Missing

**Problem:** `kafka.errors.UnknownTopicOrPartitionError`

**Solution:**
```bash
bash scripts/init_kafka.sh

# Verify topics exist
docker exec -it sentinel-kafka kafka-topics --list --bootstrap-server localhost:9092
```

---

### Models Not Found

**Problem:** `FileNotFoundError: ml/artifacts/lstm_*.pt`

**Solution:**
```bash
# Retrain models
bash scripts/train_all_models.sh

# Verify files exist
ls -lh ml/artifacts/
```

---

### Redis Empty

**Problem:** Velocity agent returns 0 scores

**Solution:**
```bash
# Reseed Redis
python3 ml/training/build_velocity_baselines.py
python3 scripts/seed_geo_history.py

# Verify data exists
redis-cli
> KEYS vel:*
> KEYS velavg:*
```

---

### Frontend Can't Connect

**Problem:** Dashboard shows "connecting" forever

**Solution:**
```bash
# Check orchestrator is running
curl http://localhost:8000/health

# Check WebSocket
wscat -c ws://localhost:8000/ws/verdicts

# Check CORS (if needed)
# Add to orchestrator/main.py:
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

---

### Port Conflicts

**Problem:** `Address already in use`

**Solution:**
```bash
# Find process using port
lsof -i :8000
lsof -i :5173

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
ports:
  - "8001:8000"  # Use 8001 instead
```

---

## 📊 Performance Tuning

### Optimize Orchestrator

```bash
# Increase workers
uvicorn orchestrator.main:app --workers 4

# Increase timeout
# In orchestrator/main.py:
AGENT_TIMEOUT = 2.0  # Increase from 1.0
```

### Optimize Redis

```bash
# Increase memory
# In docker-compose.yml:
command: ["redis-server", "--maxmemory", "1gb"]
```

### Optimize Neo4j

```bash
# Increase heap
# In docker-compose.yml:
environment:
  NEO4J_dbms_memory_heap_max__size: 2G
```

---

## 🎯 Quick Commands Reference

```bash
# Start everything
bash scripts/start_all.sh

# Stop everything
docker compose down
pkill -f uvicorn
pkill -f vite

# View logs
tail -f orchestrator.log
tail -f frontend.log

# Run tests
python3 -m pytest tests/ -v

# Check status
curl http://localhost:8000/health
curl http://localhost:8000/stats

# Interactive menu
bash scripts/quick.sh
```

---

Next: [05 - Agent Details](./05-agents.md)
