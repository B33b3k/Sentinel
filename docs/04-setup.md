# 04 — Setup & Deployment

The full, maintained setup instructions live in **[/SETUP.md](../SETUP.md)** — prerequisites,
one-command start, local-dev workflow (dockerized infra + local orchestrator), service
management, and troubleshooting. This page gives the shape of what gets deployed so the rest of
the technical docs make sense.

## What `bash scripts/start_all.sh` brings up

One command provisions the whole stack (and generates seed data / trains models if they're
missing):

1. **Infrastructure** — Kafka, Redis, Neo4j, Postgres, MLflow.
2. **State** — initializes Kafka topics, seeds Redis velocity baselines, loads the Neo4j graph.
3. **Application** — builds and starts the FastAPI orchestrator and the React dashboard.

## Service map

```
┌─────────────┐  WebSocket + REST   ┌──────────────────┐
│  Frontend   │ ──────────────────▶ │   Orchestrator   │
│  (React)    │  :3000              │   (FastAPI) :8000│
└─────────────┘                     └──────┬───────────┘
                                           │
        ┌──────────┬──────────┬────────────┼──────────┐
        ▼          ▼          ▼            ▼          ▼
     ┌──────┐  ┌──────┐   ┌──────┐    ┌────────┐  ┌────────┐
     │Kafka │  │Redis │   │Neo4j │    │Postgres│  │MLflow  │
     │:9092 │  │:6379 │   │:7687 │    │:5432   │  │:5050   │
     └──────┘  └──────┘   └──────┘    └────────┘  └────────┘
```

| Service | URL | Credentials |
|---------|-----|-------------|
| Dashboard | http://localhost:3000 | — |
| Orchestrator API (`/docs`) | http://localhost:8000 | — |
| MLflow | http://localhost:5050 | — |
| Neo4j browser | http://localhost:7474 | `neo4j` / `sentinelpass` |

> The dashboard is served at `:3000` by the Docker stack. When running the frontend locally with
> `npm run dev`, Vite serves it at `:5173` instead.

## Configuration

Connections default to `localhost` in code and are overridden by the docker-compose environment
to the internal hostnames (`kafka:29092`, `redis`, `neo4j`, `postgres`). Toggle `KAFKA_ENABLED`
to switch between the Kafka stream and direct `POST /score` scoring. See `.env.example` for the
full set of variables.

## Verifying the install

```bash
python3 -m pytest -q                    # test suite
curl http://localhost:8000/health       # orchestrator liveness
python3 scripts/benchmark_synthetic.py  # end-to-end latency + detection (see 07-performance.md)
```

---

Next: [05 — Agents](./05-agents.md)
