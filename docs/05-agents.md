# 05 - Agent Details

## 🤖 The Four Specialized Agents

Each agent is an expert in detecting one type of fraud pattern. They run in parallel and vote on every transaction.

---

## 1️⃣ Velocity Agent

### Purpose
Detect unusual transaction frequency and amount spikes.

### Algorithm

```python
def score(tx: TransactionEvent) -> AgentScore:
    # 1. Count transactions in each time window
    windows = {"2m": 120, "10m": 600, "1h": 3600, "24h": 86400}
    
    for window_name, window_seconds in windows.items():
        # Count recent transactions
        current_count = redis.zcount(
            f"vel:{tx.account_id}",
            now - window_seconds,
            now
        )
        
        # Compare to historical average
        historical_avg = redis.get(f"velavg:{tx.account_id}:{window_name}")
        frequency_ratio = current_count / max(historical_avg, 1)
        
        # Apply burst multiplier
        burst_threshold = BURST_MULTIPLIERS[window_name]
        if frequency_ratio > burst_threshold:
            frequency_score = min(frequency_ratio / burst_threshold, 1.0)
    
    # 2. Check amount anomaly
    historical_avg_amount = redis.get(f"amtavg:{tx.account_id}")
    amount_ratio = tx.amount_npr / max(historical_avg_amount, 1)
    amount_score = min(amount_ratio / 10.0, 1.0)  # 10× = max score
    
    # 3. Take worst signal (max)
    final_score = max(frequency_score, amount_score)
    
    return AgentScore(
        agent="velocity",
        score=final_score,
        reason_codes=build_reason_codes(),
        latency_ms=elapsed_ms
    )
```

### Why This Works

**Frequency Detection:**
- Multiple time windows catch different attack patterns
- 2m window: Catches rapid-fire attacks
- 24h window: Catches sustained campaigns
- Burst multipliers: 5× in 2m is worse than 2× in 24h

**Amount Detection:**
- Compares to personal history (not global average)
- Catches both large spikes and many small transactions
- Log-scale scoring (10× amount = max score)

### Data Structures

```python
# Redis keys:
vel:{account_id}              # Sorted set: tx_id → timestamp
velavg:{account_id}:2m        # String: historical count
velavg:{account_id}:10m       # String: historical count
velavg:{account_id}:1h        # String: historical count
velavg:{account_id}:24h       # String: historical count
amtavg:{account_id}           # String: historical avg amount
```

### Performance
- **Latency:** ~2 ms median, 8 ms P99 (measured — see [07-performance.md](./07-performance.md))
- **Why fast:** Redis in-memory, sorted sets optimized for time-range queries
- **Bottleneck:** Network round-trip to Redis

### Reason Codes
```python
"freq_burst_2m:count=15_avg=2"   # 15 tx in 2m, avg is 2
"amount_spike:70x"                # 70× normal amount
"velocity_normal"                 # No anomaly detected
```

### Fraud Types Caught
- Account takeover (burst of transactions)
- Automated attacks (high frequency)
- Amount testing (many small tx before large one)

---

## 2️⃣ Geo Agent

### Purpose
Detect location and device anomalies.

### Algorithm

```python
def score(tx: TransactionEvent) -> AgentScore:
    score = 0.0
    reasons = []
    
    # 1. New device check
    account_history = redis.get(f"geo:hist:{tx.account_id}")
    if tx.device_id not in account_history.known_devices:
        if tx.account_age_days > 30:
            score = 0.80  # Established account, new device = high risk
        else:
            score = 0.50  # New account, new device = medium risk
        reasons.append("new_device")
    
    # 2. Geo-velocity check (impossible travel)
    last_tx = account_history.last_transaction
    if last_tx:
        distance_km = geodesic(
            (last_tx.geo_lat, last_tx.geo_lon),
            (tx.geo_lat, tx.geo_lon)
        ).km
        
        time_hours = (tx.timestamp - last_tx.timestamp).total_seconds() / 3600
        implied_speed_kmh = distance_km / max(time_hours, 0.01)
        
        if implied_speed_kmh > 800:  # Faster than plane
            score = 0.95
            reasons.append(f"geo_velocity_impossible:{int(implied_speed_kmh)}kmh")
    
    # 3. VPN/Proxy detection
    if tx.ip_address in VPN_IP_RANGES:
        score += 0.15  # Additive (suspicious but not conclusive)
        reasons.append("vpn_or_proxy")
    
    # 4. SIM recency check
    if redis.exists(f"sim_changed:{tx.account_id}"):
        score = max(score, 0.92)  # Very high risk
        reasons.append("sim_changed_recently")
    
    return AgentScore(
        agent="geo",
        score=min(score, 1.0),
        reason_codes=reasons,
        latency_ms=elapsed_ms
    )
```

### Why This Works

**New Device:**
- Established accounts rarely change devices
- New device + high amount = takeover pattern
- Age-based scoring (new accounts expected to have new devices)

**Geo-Velocity:**
- Physics-based (can't travel 1000km in 1 hour)
- Catches SIM-swap (fraudster in different city)
- Catches device theft (thief in different location)

**VPN Detection:**
- Fraudsters use VPNs to hide location
- Legitimate users rarely use VPNs for banking
- Additive signal (not conclusive alone)

**SIM Recency:**
- Recent SIM change + transaction = high risk
- Catches SIM-swap attacks in progress
- 48-hour window (fraudster acts quickly)

### Data Structures

```python
# Redis keys:
geo:hist:{account_id}  # JSON: {
#   "known_devices": ["device_1", "device_2"],
#   "last_5_locations": [
#     {"lat": 27.7, "lon": 85.3, "timestamp": "..."},
#     ...
#   ]
# }

sim_changed:{account_id}  # Flag with 48h TTL
```

### Performance
- **Latency:** ~1 ms median, 3 ms P99 (measured — see [07-performance.md](./07-performance.md))
- **Why fast:** Simple calculations, Redis lookup
- **Bottleneck:** Geodesic distance calculation

### Reason Codes
```python
"new_device"                          # Unknown device
"geo_velocity_impossible:1200kmh"     # Impossible travel speed
"vpn_or_proxy"                        # VPN IP detected
"sim_changed_recently"                # SIM changed in last 48h
```

### Fraud Types Caught
- SIM-swap attacks (location + SIM change)
- Device theft (new device + distant location)
- Account takeover (new device)
- VPN-based fraud (proxy detection)

---

## 3️⃣ Behavior Agent

### Purpose
Detect unusual transaction patterns using ML.

### Algorithm

```python
def score(tx: TransactionEvent) -> AgentScore:
    # 1. Determine cohort and onboarding stage
    cohort = get_cohort(tx.account_id)
    stage = get_onboarding_stage(tx.account_age_days)
    
    # 2. Handle cold-start (days 0-3)
    if stage == "rules_only":
        # Apply NRB regulatory limits
        if tx.amount_npr > NRB_DAILY_LIMIT:
            return AgentScore(agent="behavior", score=0.95, 
                            reason_codes=["nrb_limit_exceeded"])
        return AgentScore(agent="behavior", score=0.0, 
                        reason_codes=["rules_passed"])
    
    # 3. Extract features
    features = extract_features(tx)
    # [log(amount), sin(hour), cos(hour), day_of_week, is_weekend,
    #  amount_zscore, inter_tx_interval, merchant_seen, *tx_type_onehot]
    
    # 4. Get transaction sequence
    sequence = redis.lrange(f"behavior:seq:{tx.account_id}", 0, 19)
    
    # 5. Run Isolation Forest
    if_model = load_if_model(cohort)
    if_score = if_model.decision_function([features])[0]
    if_score = sigmoid(if_score)  # Normalize to [0, 1]
    
    # 6. Run LSTM (if enough history)
    if len(sequence) >= 5:
        lstm_model = load_lstm_model(cohort)
        lstm_input = prepare_sequence(sequence)
        lstm_score = lstm_model(lstm_input).item()
    else:
        lstm_score = if_score  # Fallback to IF only
    
    # 7. Ensemble
    final_score = 0.6 * lstm_score + 0.4 * if_score
    
    # 8. Apply onboarding blend
    if stage == "hybrid":
        personal_weight = (tx.account_age_days - 14) / 16
        cohort_weight = 1 - personal_weight
        # (In hackathon: stay on cohort model for simplicity)
    
    return AgentScore(
        agent="behavior",
        score=final_score,
        reason_codes=[f"mode:ensemble_cohort={cohort}"],
        latency_ms=elapsed_ms
    )
```

### Why This Works

**Isolation Forest:**
- Unsupervised (doesn't need fraud labels)
- Detects outliers (unusual patterns)
- Fast inference (~10ms)
- Good for rare events

**LSTM:**
- Learns temporal patterns (time-of-day, day-of-week)
- Captures sequences (normal flow of transactions)
- Supervised (trained on fraud labels)
- Better accuracy than IF alone

**Ensemble:**
- Combines strengths of both
- IF catches novel fraud (not in training)
- LSTM catches known patterns
- 60/40 split (LSTM weighted higher)

**Cohort Models:**
- Overseas workers ≠ students ≠ businesses
- Each cohort has different normal behavior
- 6 cohorts cover 99% of accounts
- Solves cold-start problem

### Features Explained

```python
log(amount)              # Log-scale (1K and 10K closer than 10K and 100K)
sin(hour * 2π/24)        # Cyclical (23:00 and 01:00 are close)
cos(hour * 2π/24)        # Cyclical encoding
day_of_week              # 0-6 (Monday-Sunday)
is_weekend               # Binary
amount_zscore            # How many std devs from personal mean
inter_tx_interval        # Seconds since last transaction
merchant_seen_before     # Binary (new merchant = risky)
*tx_type_onehot          # [P2P, QR, SWIFT, ATM] one-hot encoded
```

### LSTM Architecture

```python
class BehaviorLSTM(nn.Module):
    def __init__(self, input_dim=11, hidden_dim=64):
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=2,
                           batch_first=True, dropout=0.2)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(),
            nn.Linear(32, 1), nn.Sigmoid()
        )
    
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])  # Last timestep
```

**Why this architecture?**
- 2 LSTM layers: Captures complex patterns
- 64 hidden units: Balance between capacity and speed
- Dropout 0.2: Prevents overfitting
- Small head: Fast inference
- Sigmoid output: Probability [0, 1]

### Training

```python
# Per cohort:
- Dataset: ~15K transactions (80/20 train/val split)
- Loss: Binary cross-entropy
- Optimizer: Adam (lr=1e-3)
- Epochs: 20
- Batch size: 64
- Early stopping: Patience 3
- Metrics: AUC, Recall@2%FPR
```

### Performance
- **Latency:** ~7 ms median, 19 ms P99 — the slowest agent (measured — see [07-performance.md](./07-performance.md))
- **Why slower:** LSTM inference + feature extraction
- **Optimization:** Could use ONNX (2× faster)

### Reason Codes
```python
"mode:ensemble_cohort=savings_urban"  # Which model used
"mode:if_only"                        # Not enough history for LSTM
"nrb_limit_exceeded"                  # Regulatory limit
"rules_passed"                        # Cold-start rules OK
```

### Fraud Types Caught
- Unusual amounts (too high or too low)
- Unusual timing (2am transactions)
- Unusual merchants (never seen before)
- Unusual patterns (sequence anomalies)

---

## 4️⃣ GNN Agent

### Purpose
Detect money laundering networks (mule rings).

### Algorithm

```python
def score(tx: TransactionEvent) -> AgentScore:
    # Check cache first
    cached = redis.get(f"gnn:{tx.account_id}")
    if cached:
        return cached
    
    # Run Cypher query to detect mule patterns
    query = """
    MATCH (sources:Account)-[t1:TRANSFERRED]->(mule:Account)
          -[t2:TRANSFERRED]->(dest:Account)
    WHERE mule.id = $account_id
      AND t1.timestamp > datetime() - duration('P1D')
      AND t2.timestamp > t1.timestamp
      AND t2.timestamp < t1.timestamp + duration('PT2H')
    WITH mule, dest,
         count(DISTINCT sources) AS source_count,
         sum(t1.amount) AS inflow,
         sum(t2.amount) AS outflow
    WHERE source_count >= 3 
      AND outflow >= 0.7 * inflow
    RETURN source_count, inflow, outflow
    """
    
    result = neo4j.run(query, account_id=tx.account_id)
    
    if result:
        # Mule pattern detected
        source_count = result[0]["source_count"]
        score = min(0.3 + (source_count * 0.15), 0.95)
        reasons = [f"mule_ring_detected:sources={source_count}"]
    else:
        score = 0.05
        reasons = ["no_mule_pattern"]
    
    # Cache result (1 hour TTL)
    redis.setex(f"gnn:{tx.account_id}", 3600, score)
    
    return AgentScore(
        agent="gnn",
        score=score,
        reason_codes=reasons,
        latency_ms=elapsed_ms
    )
```

### Why This Works

**Mule Ring Pattern:**
```
Source1 ──┐
Source2 ──┼──> Mule ──> Destination
Source3 ──┘
```

**Detection Logic:**
1. Multiple sources (3+) send to one account
2. That account quickly forwards to one destination
3. Within 2 hours (layering phase)
4. 70%+ of inflow becomes outflow (minus mule fee)

**Why Cypher (not GraphSAGE)?**
- Cypher works immediately (no training)
- Explainable (see the query)
- Fast with caching (42ms)
- GraphSAGE is stretch goal

### Graph Schema

```cypher
CREATE (a:Account {
    id: "ACC_001",
    type: "SAVINGS",
    district: "Kathmandu",
    age_days: 365
})

CREATE (a)-[:TRANSFERRED {
    amount: 50000.0,
    timestamp: datetime()
}]->(b)
```

### Performance
- **Latency:** ~1 ms median, 3 ms P99 with the Redis cache warm (measured — see [07-performance.md](./07-performance.md))
- **Why fast:** Cached results, indexed queries
- **Bottleneck:** Graph traversal (if cache miss)

### Reason Codes
```python
"mule_ring_detected:sources=5"  # 5 sources detected
"no_mule_pattern"               # No pattern found
"graph_unavailable"             # Neo4j down (fallback)
```

### Fraud Types Caught
- Mule rings (money laundering)
- Layering schemes (rapid transfers)
- Smurfing (many small sources)

---

## Agent Comparison

| Agent | Type | Latency | Fraud Types | Accuracy |
|-------|------|---------|-------------|----------|
| Velocity | Heuristic | 15ms | Burst, takeover | High |
| Geo | Heuristic | 25ms | SIM-swap, theft | High |
| Behavior | ML | 68ms | Patterns, amounts | Very High |
| GNN | Graph | 42ms | Mule rings | High |

### Why Multiple Agents?

**1. Specialization**
- Each agent is expert in one fraud type
- Better than one generalist model

**2. Robustness**
- If one agent fails, others still work
- Ensemble voting reduces false positives

**3. Explainability**
- See which agent flagged what
- Clear reason codes per agent

**4. Performance**
- Parallel execution: end-to-end P99 ~19 ms (bounded by the slowest agent), vs ~31 ms summed
- Heuristic agents fast, ML agent accurate

---

Next: [06 - Data Flow](./06-data-flow.md)
