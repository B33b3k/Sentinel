# 06 - Data Flow

## Complete Transaction Journey

### Overview

```
Transaction → Adapter → Orchestrator → 4 Agents → Synthesis → Verdict → Output
     ↓           ↓           ↓            ↓          ↓         ↓        ↓
   Kafka      Schema    Parallel      Scoring    Voting   Decision  Audit
```

---

## Phase 1: Ingestion

### Real-World Flow (Production)

```
Bank Core System
    ↓ (REST/SOAP)
Transaction Gateway
    ↓ (JSON)
Kafka Producer
    ↓
Topic: sentinel.transactions
    ↓
Orchestrator Consumer
```

### Demo Flow (Hackathon)

```
Synthetic Data (Parquet)
    ↓
Replay Script
    ↓
Kafka Topic
    ↓
Orchestrator Consumer
```

### Data Format

**Input (Unknown - Will be provided):**
```json
{
  "txn_id": "...",
  "acct_no": "...",
  "txn_amt": 85000,
  "txn_timestamp": "...",
  ...
}
```

**After Adapter:**
```python
TransactionEvent(
    transaction_id=UUID("..."),
    account_id="ACC_SITA_001",
    timestamp=datetime(...),
    amount_npr=85000.0,
    currency="NPR",
    transaction_type="QR_ESEWA",
    counterparty_id="MERCHANT_UNKNOWN_42",
    device_id="device_unknown_new",
    ip_address="103.69.1.1",
    geo_lat=26.8141,
    geo_lon=87.2792,
    geo_city="Dharan",
    geo_district="Dharan",
    account_age_days=720,
    account_home_district="Kathmandu",
    account_type="SAVINGS"
)
```

**Why Adapter Pattern?**
- Real format unknown until hackathon day
- Change ONE file when format arrives
- Zero agent changes needed
- Graceful fallback for missing fields

---

## Phase 2: Orchestration

### Parallel Execution

```python
async def process_transaction(tx: TransactionEvent):
    t0 = time.perf_counter()
    
    # Run all 4 agents in parallel
    vel, geo, beh, gnn = await asyncio.gather(
        asyncio.to_thread(velocity_agent.score, tx),
        asyncio.to_thread(geo_agent.score, tx),
        asyncio.to_thread(behavior_agent.score, tx),
        asyncio.to_thread(gnn_agent.score, tx),
    )
    
    # Synthesize verdict
    verdict = synthesis.synthesize(tx, [vel, geo, beh, gnn])
    verdict.total_latency_ms = (time.perf_counter() - t0) * 1000
    
    return verdict
```

**Why asyncio.gather?**
- Runs all agents simultaneously
- Total time = max(agent times), not sum
- Better CPU utilization
- See [07-performance.md](./07-performance.md) for measured latency

**Timeout Handling:**
```python
try:
    score = await asyncio.wait_for(
        asyncio.to_thread(agent.score, tx),
        timeout=1.0  # 1 second max per agent
    )
except asyncio.TimeoutError:
    score = AgentScore(
        agent="...",
        score=0.5,  # Neutral (don't bias verdict)
        reason_codes=["agent_timeout"],
        latency_ms=1000.0
    )
```

---

## Phase 3: Agent Scoring

### Velocity Agent Data Flow

```
Transaction
    ↓
Redis: vel:{account_id}
    ↓ ZCOUNT (time range)
Current count: 15
    ↓
Redis: velavg:{account_id}:2m
    ↓
Historical avg: 2
    ↓
Ratio: 15/2 = 7.5
    ↓
Score: 0.75 (high)
    ↓
AgentScore(agent="velocity", score=0.75, ...)
```

**Data Dependencies:**
- Redis: Transaction history (sorted sets)
- Redis: Historical baselines (strings)

---

### Geo Agent Data Flow

```
Transaction
    ↓
Redis: geo:hist:{account_id}
    ↓
Last location: Kathmandu (27.7, 85.3)
Current location: Dharan (26.8, 87.3)
    ↓
Distance: 800 km
Time: 30 minutes
    ↓
Speed: 1600 km/h (impossible!)
    ↓
Score: 0.95 (very high)
    ↓
AgentScore(agent="geo", score=0.95, ...)
```

**Data Dependencies:**
- Redis: Location history (JSON)
- Redis: Known devices (set)
- Redis: SIM change flag (TTL key)

---

### Behavior Agent Data Flow

```
Transaction
    ↓
Extract features
    ↓ [log(amount), sin(hour), ...]
Redis: behavior:seq:{account_id}
    ↓
Last 20 transactions
    ↓
Load models: IF + LSTM (cohort=savings_urban)
    ↓
IF score: 0.82
LSTM score: 0.88
    ↓
Ensemble: 0.6*0.88 + 0.4*0.82 = 0.856
    ↓
AgentScore(agent="behavior", score=0.856, ...)
```

**Data Dependencies:**
- Redis: Transaction sequence (list)
- Filesystem: Trained models (LSTM + IF)
- Redis: Cohort assignment (string)

---

### GNN Agent Data Flow

```
Transaction
    ↓
Redis: gnn:{account_id} (cache check)
    ↓ MISS
Neo4j: Run Cypher query
    ↓
MATCH (sources)->(mule)->(dest)
WHERE mule.id = "ACC_001"
    ↓
Result: 5 sources found
    ↓
Score: 0.3 + (5 * 0.15) = 1.05 → 0.95 (capped)
    ↓
Redis: Cache result (1h TTL)
    ↓
AgentScore(agent="gnn", score=0.95, ...)
```

**Data Dependencies:**
- Neo4j: Account graph (nodes + edges)
- Redis: Query result cache (strings)

---

## Phase 4: Synthesis

### Context-Aware Weighting

```
Transaction type: QR_ESEWA
    ↓
Select weights: {velocity: 0.35, geo: 0.40, behavior: 0.25, gnn: 0.00}
    ↓
Agent scores: {velocity: 0.75, geo: 0.95, behavior: 0.85, gnn: 0.05}
    ↓
Composite = 0.35*0.75 + 0.40*0.95 + 0.25*0.85 + 0.00*0.05
          = 0.2625 + 0.38 + 0.2125 + 0
          = 0.855
    ↓
Apply thresholds:
  < 0.40 → ALLOW
  0.40-0.75 → OTP_INTERLOCK
  > 0.75 → BLOCK
    ↓
Verdict: BLOCK (0.855 > 0.75)
```

**Why Context-Aware?**
- QR payments: Geo matters most (location fraud)
- SWIFT: Graph matters most (layering)
- P2P: Balanced (all signals relevant)

**Weight Matrix:**
```python
WEIGHTS_BY_TYPE = {
    "P2P":              {"velocity": 0.20, "geo": 0.30, "behavior": 0.30, "gnn": 0.20},
    "QR_ESEWA":         {"velocity": 0.35, "geo": 0.40, "behavior": 0.25, "gnn": 0.00},
    "SWIFT_REMITTANCE": {"velocity": 0.15, "geo": 0.25, "behavior": 0.20, "gnn": 0.40},
    "ATM_POS":          {"velocity": 0.30, "geo": 0.45, "behavior": 0.25, "gnn": 0.00},
}
```

---

## Phase 5: OTP Interlock (If Needed)

### Trigger Flow

```
Verdict: OTP_INTERLOCK
    ↓
Freeze transaction in Postgres
    ↓
Generate 2 OTPs (6-digit codes)
    ↓
┌─────────────────┬─────────────────┐
│   Send SMS      │   Send Email    │
│ (Sparrow/Twilio)│   (SMTP)        │
└────────┬────────┴────────┬────────┘
         │                 │
    Store in Redis (TTL 5 min)
         │
    otp_pending:{tx_id} = {
        sms_otp: "123456",
        email_otp: "789012",
        phone: "+977-...",
        email: "...",
        triggered_at: timestamp
    }
         ↓
    Return to customer
```

### Verification Flow

```
Customer submits codes
    ↓
POST /otp/confirm
    {tx_id, sms_code, email_code}
    ↓
Redis: otp_pending:{tx_id}
    ↓
Compare codes
    ↓
┌──────────────┬──────────────┬──────────────┐
│ Both ✓       │ SMS ✓ only   │ Email ✓ only │
│ RELEASE      │ BLOCK        │ HUMAN_REVIEW │
│              │ (SIM-swap!)  │              │
└──────────────┴──────────────┴──────────────┘
    ↓
Update transaction status
    ↓
Kafka: sentinel.otp_events
```

**Why Dual-Path?**
- Fraudster can duplicate SIM (SMS compromised)
- Fraudster can't access email (independent)
- SMS-only pass = SIM-swap detected!

---

## Phase 6: Output & Audit

### Multi-Channel Output

```
Verdict
    ├─→ Kafka: sentinel.verdicts
    │   (for downstream systems)
    │
    ├─→ Postgres: audit_log
    │   (compliance & investigation)
    │
    ├─→ WebSocket: /ws/verdicts
    │   (live dashboard updates)
    │
    └─→ HTTP Response
        (if synchronous call)
```

### Audit Log Schema

```sql
CREATE TABLE audit_log (
    transaction_id UUID PRIMARY KEY,
    account_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Verdict
    verdict TEXT NOT NULL,
    composite_score FLOAT NOT NULL,
    
    -- Agent details
    agent_scores JSONB NOT NULL,
    weights_used JSONB NOT NULL,
    
    -- Context
    transaction_type TEXT,
    amount_npr FLOAT,
    total_latency_ms FLOAT,
    
    -- Indexes
    INDEX idx_account_id (account_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_verdict (verdict)
);
```

**Why Audit Everything?**
- Regulatory compliance (NRB requirements)
- Investigation (why was this blocked?)
- Model improvement (feedback loop)
- Dispute resolution (customer complaints)

---

## Feedback Loop

### Retraining Pipeline

```
Audit Log
    ↓
Weekly batch job
    ↓
Extract features + labels
    ↓
Retrain models (LSTM + IF)
    ↓
MLflow: Log new experiments
    ↓
Compare metrics (AUC, recall, FPR)
    ↓
If better: Promote to Production
    ↓
Update model files
    ↓
Agents reload models (hot reload)
```

**Kafka Topic: sentinel.retraining**
```json
{
  "trigger": "scheduled",
  "timestamp": "...",
  "metrics": {
    "recall": "<recall>",
    "fpr": "<fpr>",
    "auc": "<auc>"
  }
}
```

See [07-performance.md](./07-performance.md) for measured model metrics.

---

## Data Volume Estimates

### Per Transaction

| Component | Data Size | Storage |
|-----------|-----------|---------|
| TransactionEvent | ~500 bytes | Kafka |
| Agent scores (4×) | ~200 bytes | Memory |
| Verdict | ~800 bytes | Kafka + Postgres |
| Audit log | ~1 KB | Postgres |
| **Total** | **~2.5 KB** | |

### At Scale

**10,000 TPS:**
- Kafka throughput: 25 MB/s
- Postgres writes: 10K rows/s
- Redis operations: 40K ops/s (4 agents × 10K)
- Neo4j queries: 1K/s (with 90% cache hit)

**Daily Volume:**
- Transactions: 864 million
- Audit log: 2.1 TB/day
- Kafka retention: 7 days = 15 TB

---

## Data Access Patterns

### Read-Heavy

**Redis (Velocity):**
- Read: 10K TPS (ZCOUNT, GET)
- Write: 10K TPS (ZADD, SET)
- Ratio: 1:1

**Redis (Geo):**
- Read: 10K TPS (GET)
- Write: 10K TPS (SET)
- Ratio: 1:1

**Neo4j (GNN):**
- Read: 10K TPS (Cypher queries)
- Write: 10K TPS (CREATE edges)
- Cache hit: 90% → 1K actual queries/s
- Ratio: 9:1 (read-heavy)

### Write-Heavy

**Postgres (Audit):**
- Read: 100 TPS (investigations)
- Write: 10K TPS (audit log)
- Ratio: 1:100 (write-heavy)

**Kafka:**
- Write: 10K TPS (verdicts)
- Read: 10K TPS (consumers)
- Ratio: 1:1

---

## Data Flow Optimization

### Caching Strategy

**L1: In-Memory (Agent)**
```python
# Model cache (loaded once)
_models = {}

def load_model(cohort):
    if cohort not in _models:
        _models[cohort] = torch.load(f"ml/artifacts/lstm_{cohort}.pt")
    return _models[cohort]
```

**L2: Redis (Shared)**
```python
# Query result cache (1h TTL)
cached = redis.get(f"gnn:{account_id}")
if cached:
    return cached
```

**L3: Database (Persistent)**
```python
# Audit log (permanent)
postgres.execute("INSERT INTO audit_log ...")
```

### Batch Operations

**Redis Pipeline:**
```python
pipe = redis.pipeline()
pipe.zadd(f"vel:{account_id}", {tx_id: timestamp})
pipe.get(f"velavg:{account_id}:2m")
pipe.get(f"amtavg:{account_id}")
results = pipe.execute()  # Single round-trip
```

**Postgres Batch Insert:**
```python
# Buffer 100 verdicts, insert in one query
if len(buffer) >= 100:
    postgres.executemany("INSERT INTO audit_log ...", buffer)
```

---

Next: [07 - Performance](./07-performance.md)
