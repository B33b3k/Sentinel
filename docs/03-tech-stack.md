# 03 - Technology Stack

## Technology Choices & Justifications

### Backend Stack

#### Python 3.12
**Why Python?**
- Rich ML ecosystem (PyTorch, scikit-learn)
- Fast development (hackathon time constraint)
- Type hints (Pydantic for safety)
- Async support (asyncio for parallel agents)
- Slower than Go/Rust, but adequate for the latency budget (see [07-performance.md](./07-performance.md) for measured latency)

**Alternatives considered:**
- Go: Faster but weaker ML libraries
- Java: Enterprise-ready but verbose
- Rust: Fastest but steep learning curve

**Decision:** Python for ML support and development speed

---

#### FastAPI
**Why FastAPI?**
- Async/await (parallel agent execution)
- Type safety (Pydantic schemas)
- Auto-generated docs (Swagger UI)
- WebSocket support (live dashboard updates)
- Built on Starlette + uvicorn

**Alternatives considered:**
- Flask: Simpler but no async, no type safety
- Django: Too heavy for this use case
- Express.js: Would need Node.js (different ecosystem)

**Decision:** FastAPI for an async ML service

---

#### PyTorch 2.x
**Why PyTorch?**
- Dynamic graphs (easier debugging)
- Pythonic API (faster development)
- Strong community (more examples)
- TorchScript (inference optimization)

**Alternatives considered:**
- TensorFlow: More mature deployment tooling but verbose
- JAX: Fast but less mature
- scikit-learn only: No deep learning

**Decision:** PyTorch for LSTM, scikit-learn for IF

---

#### scikit-learn
**Why scikit-learn?**
- Mature and stable
- Fast training (Isolation Forest in seconds)
- Simple API (fit/predict)
- Good documentation

**For:** Isolation Forest (anomaly detection)

---

### Infrastructure Stack

#### Apache Kafka
**Why Kafka?**
- Decouples ingestion from processing
- Handles backpressure (if agents slow)
- Replay capability (testing/debugging)
- Scalable (add consumers)
- Widely used for event streaming

**Alternatives considered:**
- RabbitMQ: Simpler but less scalable
- Redis Streams: Lighter but less features
- Direct HTTP: No buffering, no replay

**Decision:** Kafka for event streaming

**Topics:**
```
sentinel.transactions  → Incoming transactions
sentinel.verdicts      → Fraud verdicts
sentinel.otp_events    → OTP lifecycle
sentinel.retraining    → Model feedback loop
```

---

#### Redis 7
**Why Redis?**
- In-memory (sub-millisecond lookups)
- Sorted sets (time-range queries)
- TTL support (auto-cleanup)
- Atomic operations (thread-safe)
- Simple (no complex setup)

**Alternatives considered:**
- Memcached: Simpler but no sorted sets
- PostgreSQL: Persistent but slower
- In-memory dict: No persistence, no TTL

**Decision:** Redis for the velocity agent

**Use cases:**
- Velocity windows (sorted sets)
- Historical baselines (strings)
- Geo history (JSON blobs)
- OTP state (hash with TTL)
- GNN cache (query results)

---

#### Neo4j 5 Community
**Why Neo4j?**
- Native graph database (optimized for relationships)
- Cypher query language (expressive)
- Graph algorithms (GDS library)
- Visualization (browser UI)
- Free community edition

**Alternatives considered:**
- PostgreSQL + recursive CTEs: Slow for graphs
- NetworkX: In-memory only, no persistence
- Amazon Neptune: Cloud-only, expensive

**Decision:** Neo4j for graph queries

**Schema:**
```cypher
(:Account {id, type, district, age_days})
-[:TRANSFERRED {amount, timestamp}]->
(:Account)
```

---

#### PostgreSQL 16
**Why PostgreSQL?**
- ACID compliance (audit trail)
- JSON support (flexible schema)
- Mature and stable
- Free and open source

**Alternatives considered:**
- MySQL: Similar but weaker JSON support
- MongoDB: NoSQL but need ACID for audit
- SQLite: Too simple for production

**Decision:** PostgreSQL for audit logging

**Schema:**
```sql
CREATE TABLE audit_log (
    transaction_id UUID PRIMARY KEY,
    account_id TEXT,
    verdict TEXT,
    composite_score FLOAT,
    agent_scores JSONB,
    weights_used JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
```

---

#### MLflow 2.x
**Why MLflow?**
- Experiment tracking (compare models)
- Model registry (version control)
- Artifact storage (save models)
- UI dashboard (visualize metrics)
- Open source (no vendor lock-in)

**Alternatives considered:**
- Weights & Biases: Better UI but cloud-only
- TensorBoard: PyTorch-only
- Custom logging: Reinventing the wheel

**Decision:** MLflow for experiment tracking and model registry

**Tracked:**
- 12 model training runs (6 cohorts × 2 models)
- Hyperparameters (learning rate, epochs)
- Metrics (AUC, recall, FPR)
- Artifacts (model files)

---

### Frontend Stack

#### React 18 + TypeScript
**Why React?**
- Component-based (reusable)
- Virtual DOM (fast updates)
- Large ecosystem (libraries)
- Widely adopted

**Why TypeScript?**
- Type safety (catch bugs early)
- Better IDE support (autocomplete)
- Self-documenting code

**Alternatives considered:**
- Vue: Simpler but smaller ecosystem
- Svelte: Faster but less mature
- Plain JavaScript: No type safety

**Decision:** React + TS for the dashboard UI

---

#### Vite
**Why Vite?**
- Fast dev server (instant HMR)
- Fast builds (esbuild)
- Modern (ES modules)
- Simple config

**Alternatives considered:**
- Create React App: Slower, deprecated
- Webpack: Complex configuration
- Parcel: Less control

**Decision:** Vite for speed

---

#### Tailwind CSS
**Why Tailwind?**
- Utility-first (fast development)
- No CSS files (everything in JSX)
- Consistent design (design system)
- Small bundle (purges unused)

**Alternatives considered:**
- Bootstrap: Too opinionated
- Material-UI: Heavy bundle
- Plain CSS: Slow development

**Decision:** Tailwind for rapid UI development

---

#### Recharts
**Why Recharts?**
- React-native (composable)
- Responsive (works on all screens)
- Customizable (full control)
- Good documentation

**Alternatives considered:**
- Chart.js: Not React-native
- D3.js: Too low-level
- Victory: Similar but heavier

**Decision:** Recharts for React integration

---

### Deployment Stack

#### Docker Compose
**Why Docker Compose?**
- Multi-container (8 services)
- Declarative (YAML config)
- Reproducible (same everywhere)
- Simple (one command startup)

**Alternatives considered:**
- Kubernetes: Overkill for demo
- Manual setup: Not reproducible
- Docker Swarm: Less popular

**Decision:** Docker Compose for local demo

**Services:**
```yaml
- zookeeper    # Kafka dependency
- kafka        # Event streaming
- redis        # Velocity cache
- neo4j        # Graph database
- postgres     # Audit log
- mlflow       # Model tracking
- orchestrator # FastAPI service
- frontend     # React app
```

---

### Development Tools

#### pytest
**Why pytest?**
- Simple syntax (assert statements)
- Fixtures (reusable setup)
- Parametrize (test multiple cases)
- Coverage reports

**Test coverage:** 96 tests pass (9 further tests are infra smoke checks that require the dockerized stack); run `python3 -m pytest -q`

---

#### Locust
**Why Locust?**
- Python-based (same language)
- Distributed (multi-machine)
- Web UI (real-time metrics)
- Scriptable (custom scenarios)

**Load test:** see [07-performance.md](./07-performance.md) for measured throughput

---

#### Black + Ruff
**Why Black?**
- Opinionated (no debates)
- Consistent (same style everywhere)
- Fast (Rust-based)

**Why Ruff?**
- Fast linter
- Replaces multiple tools (isort, flake8, etc.)

---

## Technology Comparison

### Performance Comparison

Per-component and per-agent latency choices are summarized below; for measured latency see [07-performance.md](./07-performance.md).

| Component | Technology | Alternative |
|-----------|-----------|-------------|
| Velocity | Redis | PostgreSQL |
| Geo | Python | Go |
| Behavior | PyTorch | TensorFlow |
| GNN | Neo4j | PostgreSQL |
| Orchestrator | FastAPI | Flask |

---

### Bundle Size Comparison

| Frontend | Technology | Bundle Size |
|----------|-----------|-------------|
| Framework | React | 42 KB |
| Charts | Recharts | 95 KB |
| Styling | Tailwind | 8 KB (purged) |
| Icons | Lucide | 12 KB |
| **Total** | | **~160 KB** |

---

## Technology Decisions Summary

### What We Chose & Why

1. **Python** - ML ecosystem + fast development
2. **FastAPI** - Async + type safety
3. **PyTorch** - LSTM training
4. **scikit-learn** - Isolation Forest
5. **Kafka** - Event streaming
6. **Redis** - Caching
7. **Neo4j** - Graph analytics
8. **PostgreSQL** - Audit trail
9. **MLflow** - Model tracking
10. **React + TypeScript** - Dashboard UI
11. **Tailwind** - Styling
12. **Docker Compose** - Deployment

### What We Didn't Choose & Why

1. **TensorFlow** - More verbose than PyTorch
2. **MongoDB** - Need ACID for audit
3. **RabbitMQ** - Less scalable than Kafka
4. **Vue/Svelte** - Smaller ecosystem
5. **Kubernetes** - Overkill for demo
6. **GraphQL** - REST sufficient
7. **WebSockets only** - Need REST fallback

---

## Technology Stack Summary

- **Mature components** - All technologies are widely used and stable
- **Horizontally scalable** - Stateless orchestrator; throughput scales with consumers (see [07-performance.md](./07-performance.md) for measured throughput)
- **Maintainable** - Type-safe, documented
- **Latency** - See [07-performance.md](./07-performance.md) for measured latency
- **Full stack** - Ingestion, scoring, storage, and UI covered
- **Current versions** - Recent releases of each dependency

---

Next: [04 - Setup Guide](./04-setup.md)
