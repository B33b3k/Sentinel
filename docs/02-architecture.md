# 02 - Architecture Deep Dive

## System Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│  Dashboard · Scenarios · Inspector · Stats · OTP        │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket + REST
┌────────────────────▼────────────────────────────────────┐
│              Orchestrator (FastAPI)                      │
│  Kafka Consumer · Agent Coordinator · WebSocket Server  │
└─┬────────┬────────┬────────┬────────┬────────┬──────────┘
  │        │        │        │        │        │
  ▼        ▼        ▼        ▼        ▼        ▼
┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐
│Vel │  │Geo │  │Beh │  │GNN │  │Syn │  │OTP │
└─┬──┘  └─┬──┘  └─┬──┘  └─┬──┘  └────┘  └────┘
  │       │       │       │
  ▼       ▼       ▼       ▼
┌────────────────────────────────────────────┐
│  Redis · Neo4j · Postgres · MLflow · Kafka │
└────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Transaction Ingestion

```
Real Transaction
    ↓
Kafka Topic: sentinel.transactions
    ↓
Orchestrator Kafka Consumer
    ↓
Data Adapter (if real data)
    ↓
TransactionEvent (internal schema)
```

**Why Kafka?**
- Decouples ingestion from processing
- Handles backpressure (if agents slow down)
- Replay capability (for testing/debugging)
- Scalable (add more consumers)

### 2. Parallel Agent Execution

```python
# Orchestrator runs all 4 agents in parallel
vel, geo, beh, gnn = await asyncio.gather(
    asyncio.to_thread(velocity_agent.score, tx),
    asyncio.to_thread(geo_agent.score, tx),
    asyncio.to_thread(behavior_agent.score, tx),
    asyncio.to_thread(gnn_agent.score, tx),
)
```

**Why parallel?**
- Total time = max(agent times), not sum
- Better resource utilization
- See [07-performance.md](./07-performance.md) for measured latency

### 3. Synthesis & Verdict

```
Agent Scores → Synthesis Agent
    ↓
Context-aware weighted voting
    ↓
Composite Score (0-1)
    ↓
Verdict: ALLOW | OTP_INTERLOCK | BLOCK
```

### 4. OTP Interlock (if needed)

```
Verdict = OTP_INTERLOCK
    ↓
Freeze transaction
    ↓
Send SMS OTP + Email OTP (parallel)
    ↓
Customer submits both codes
    ↓
Verify both channels
    ↓
RELEASE | BLOCK (SIM-swap) | HUMAN_REVIEW
```

### 5. Response & Audit

```
Verdict
    ├─→ Kafka Topic: sentinel.verdicts
    ├─→ Postgres Audit Log
    ├─→ WebSocket Broadcast (dashboard)
    └─→ HTTP Response (if REST call)
```

---

## Component Details

### Orchestrator (FastAPI)

**Responsibilities:**
1. Consume transactions from Kafka
2. Coordinate agent execution (parallel)
3. Handle timeouts (1s per agent)
4. Broadcast verdicts via WebSocket
5. Write audit logs to Postgres

**Why FastAPI?**
- Async/await support (parallel execution)
- Type safety (Pydantic schemas)
- Auto-generated API docs
- High performance (Starlette + uvicorn)

**Key Endpoints:**
```python
POST /score                    # Direct scoring (no Kafka)
GET  /verdicts/{tx_id}        # Lookup verdict
GET  /stats                   # System metrics
POST /scenarios/run/{name}    # Demo scenarios
WS   /ws/verdicts             # Live updates
POST /otp/confirm             # OTP verification
```

### Velocity Agent

**Algorithm:**
```python
# For each time window (2m, 10m, 1h, 24h):
current_count = redis.zcount(f"vel:{account_id}", now - window, now)
historical_avg = redis.get(f"velavg:{account_id}:{window}")
frequency_score = current_count / historical_avg

# Amount anomaly:
amount_score = tx.amount / historical_avg_amount

# Final score:
score = max(frequency_score, amount_score)  # Worst signal wins
```

**Why Redis?**
- In-memory (fast lookups)
- Sorted sets (efficient time-range queries)
- TTL support (auto-cleanup old data)
- Atomic operations (thread-safe)

**Data Structures:**
```
vel:{account_id}           → Sorted set (tx_id → timestamp)
velavg:{account_id}:2m     → String (historical count)
amtavg:{account_id}        → String (historical amount)
```

### Geo Agent

**Algorithm:**
```python
# 1. New device check
if tx.device_id not in account_history.known_devices:
    score += 0.65  # High risk

# 2. Geo-velocity check
distance_km = geodesic(last_location, current_location).km
time_hours = (current_time - last_time).total_seconds() / 3600
implied_speed = distance_km / time_hours
if implied_speed > 800:  # Impossible (plane speed)
    score = 0.95

# 3. VPN/Proxy check
if tx.ip_address in VPN_RANGES:
    score += 0.15

# 4. SIM recency check
if redis.exists(f"sim_changed:{account_id}"):
    score = 0.92
```

**Why heuristic (not ML)?**
- Geo rules are well-defined
- Fast (no model inference)
- Explainable (clear reason codes)
- Accurate (physics-based)

### Behavior Agent

**Algorithm:**
```python
# 1. Feature extraction
features = [
    log(amount),
    sin(hour_of_day * 2π / 24),  # Cyclical
    cos(hour_of_day * 2π / 24),
    day_of_week,
    is_weekend,
    amount_zscore,
    inter_tx_interval,
    merchant_seen_before,
    *one_hot(transaction_type)
]

# 2. Isolation Forest (anomaly detection)
if_score = isolation_forest.score(features)

# 3. LSTM (sequence modeling)
sequence = last_20_transactions
lstm_score = lstm_model(sequence)

# 4. Ensemble
final_score = 0.6 * lstm_score + 0.4 * if_score
```

**Why LSTM + Isolation Forest?**
- **LSTM:** Learns temporal patterns (time-of-day, day-of-week)
- **IF:** Detects outliers (unusual amounts, rare merchants)
- **Ensemble:** Combines strengths of both

**Why per-cohort models?**
- Overseas workers have different patterns than students
- Salary accounts differ from business accounts
- 6 cohorts cover 99% of accounts

### GNN Agent

**Algorithm (Cypher query):**
```cypher
// Find mule rings: 3+ sources → mule → destination within 2h
MATCH (sources:Account)-[t1:TRANSFERRED]->(mule:Account)
      -[t2:TRANSFERRED]->(dest:Account)
WHERE t1.timestamp > datetime() - duration('P1D')
  AND t2.timestamp > t1.timestamp
  AND t2.timestamp < t1.timestamp + duration('PT2H')
WITH mule, dest,
     count(DISTINCT sources) AS source_count,
     sum(t1.amount) AS inflow,
     sum(t2.amount) AS outflow
WHERE source_count >= 3 AND outflow >= 0.7 * inflow
RETURN mule.id, dest.id, source_count
```

**Why Neo4j?**
- Native graph database (optimized for relationships)
- Cypher query language (expressive)
- Graph algorithms (PageRank, community detection)
- Fast traversals (follows edges efficiently)

**Why Cypher instead of GraphSAGE?**
- Cypher works immediately (no training)
- Explainable (see the query)
- Fast enough with caching (see [07-performance.md](./07-performance.md) for measured latency)
- GraphSAGE is a stretch goal (if time permits)

### Synthesis Agent

**Algorithm:**
```python
# 1. Select weights based on transaction type
weights = WEIGHTS_BY_TYPE[tx.transaction_type]

# 2. Weighted sum
composite = sum(weights[agent] * scores[agent] for agent in weights)

# 3. Apply thresholds
if composite < 0.40:
    verdict = "ALLOW"
elif composite < 0.75:
    verdict = "OTP_INTERLOCK"
else:
    verdict = "BLOCK"
```

**Why context-aware weights?**
- QR payments: Geo matters most (location-based fraud)
- SWIFT: Graph matters most (layering schemes)
- P2P: Balanced (all signals relevant)

### OTP Interlock

**State Machine:**
```
TRIGGERED
    ↓
Send SMS + Email (parallel)
    ↓
Store in Redis (TTL 5 minutes)
    ↓
Customer submits codes
    ↓
┌─────────────┬─────────────┬─────────────┐
│ Both ✓      │ SMS ✓ only  │ Email ✓ only│
│ RELEASE     │ BLOCK       │ HUMAN_REVIEW│
│             │ (SIM-swap!) │             │
└─────────────┴─────────────┴─────────────┘
```

**Why dual-path?**
- Fraudster can duplicate SIM (SMS compromised)
- Fraudster can't access email (independent channel)
- If SMS passes but email fails → SIM-swap detected!

---

## Security Considerations

### 1. Data Adapter Pattern
**Problem:** Real data format unknown until hackathon day
**Solution:** Adapter layer isolates format changes
```
Real Data → Adapter → TransactionEvent → Agents
              ↑
         Only this changes
```

### 2. Graceful Degradation
**Problem:** Agent might fail or timeout
**Solution:** Missing agent → neutral score (0.5)
```python
if agent_timeout:
    score = 0.5  # Neutral, don't bias verdict
    reason = "agent_timeout"
```

### 3. Audit Trail
**Problem:** Need to explain every verdict
**Solution:** Log everything to Postgres
```sql
CREATE TABLE audit_log (
    transaction_id UUID,
    verdict TEXT,
    composite_score FLOAT,
    agent_scores JSONB,
    weights_used JSONB,
    timestamp TIMESTAMPTZ
);
```

---

## Scalability

### Horizontal Scaling

**Orchestrator:**
- Add more Kafka consumers (partition by account_id)
- Each consumer processes different accounts
- No coordination needed (stateless)

**Agents:**
- Velocity: Redis cluster (sharded by account_id)
- Geo: Stateless (no shared state)
- Behavior: Model replicas (load balanced)
- GNN: Neo4j cluster (read replicas)

### Vertical Scaling

**Bottleneck:** Behavior agent (the slowest agent; see [07-performance.md](./07-performance.md) for measured latency)
**Solutions:**
1. ONNX export (2× faster inference)
2. Batch inference (process 16 tx at once)
3. GPU acceleration (if available)
4. Smaller model (32 hidden units)

### Current Capacity

Throughput scales horizontally by adding Kafka consumers (partitioned by account_id), since orchestrator instances are stateless. See [07-performance.md](./07-performance.md) for measured throughput.

---

Next: [03 - Technology Choices](./03-tech-stack.md)
