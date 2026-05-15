"""SENTINEL Orchestrator — FastAPI + Kafka consumer + parallel agent execution."""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

import psycopg
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agents.behavior.agent import BehaviorAgent
from agents.geo.agent import GeoAgent
from agents.gnn.cypher_agent import GNNAgent
from agents.otp.interlock import CustomerInfo, OTPInterlock
from agents.synthesis.agent import SynthesisAgent
from agents.velocity.agent import VelocityAgent
from orchestrator.schemas import AgentScore, SynthesisVerdict, TransactionEvent

# ---------------------------------------------------------------------------
# Structured logging setup
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        __import__("logging").getLevelName(os.environ.get("LOG_LEVEL", "INFO"))
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger("sentinel.orchestrator")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "true").lower() == "true"
KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://sentinel:sentinel@localhost:5432/sentinel_audit")
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
AGENT_TIMEOUT = 1.0  # seconds per agent

# In-memory stats ring buffer
_recent_verdicts: deque = deque(maxlen=1000)
_verdict_timestamps: deque = deque(maxlen=10000)  # epoch floats for TPS
_ws_clients: set[WebSocket] = set()

# Agents (initialised in lifespan)
velocity_agent: VelocityAgent
geo_agent: GeoAgent
behavior_agent: BehaviorAgent
gnn_agent: GNNAgent
synthesis: SynthesisAgent
interlock: OTPInterlock
producer: Any = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global velocity_agent, geo_agent, behavior_agent, gnn_agent, synthesis, interlock, producer

    log.info("sentinel.startup", kafka_enabled=KAFKA_ENABLED, redis_url=REDIS_URL)

    velocity_agent = VelocityAgent(REDIS_URL)
    geo_agent = GeoAgent(REDIS_URL)
    behavior_agent = BehaviorAgent(REDIS_URL)
    gnn_agent = GNNAgent(redis_url=REDIS_URL)
    synthesis = SynthesisAgent()

    if KAFKA_ENABLED:
        try:
            from kafka import KafkaProducer
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode(),
            )
            asyncio.create_task(_kafka_consumer_loop())
            log.info("kafka.connected", servers=KAFKA_SERVERS)
        except Exception as e:
            log.warning("kafka.unavailable", error=str(e))

    interlock = OTPInterlock(redis_url=REDIS_URL, kafka_producer=producer)
    await _ensure_audit_table()
    log.info("sentinel.ready")
    yield
    if producer:
        producer.flush()
        producer.close()
    log.info("sentinel.shutdown")


app = FastAPI(title="SENTINEL Orchestrator", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

async def process_transaction(tx: TransactionEvent) -> SynthesisVerdict:
    t0 = time.perf_counter()
    tx_log = log.bind(tx_id=str(tx.transaction_id), account_id=tx.account_id, tx_type=tx.transaction_type)

    async def _run(fn, *args):
        agent_name = getattr(fn.__self__, "AGENT_NAME", fn.__self__.__class__.__name__.lower().replace("agent", ""))
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args), timeout=AGENT_TIMEOUT
            )
        except asyncio.TimeoutError:
            tx_log.warning("agent.timeout", agent=agent_name)
            return AgentScore(
                agent=agent_name, score=0.5,
                reason_codes=["agent_timeout"],
                latency_ms=AGENT_TIMEOUT * 1000,
            )

    vel, geo, beh, gnn = await asyncio.gather(
        _run(velocity_agent.score, tx),
        _run(geo_agent.score, tx),
        _run(behavior_agent.score, tx),
        _run(gnn_agent.score, tx),
    )

    verdict = synthesis.synthesize(tx, [vel, geo, beh, gnn])
    verdict.total_latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    tx_log.info(
        "verdict",
        verdict=verdict.verdict,
        composite=verdict.composite_score,
        latency_ms=verdict.total_latency_ms,
        agent_scores={s.agent: round(s.score, 3) for s in verdict.agent_scores},
    )

    if verdict.verdict == "OTP_INTERLOCK":
        customer = _get_customer(tx.account_id)
        asyncio.create_task(asyncio.to_thread(interlock.trigger, tx, customer))
        tx_log.info("otp.triggered", phone=customer.phone, email=customer.email)

    if producer:
        producer.send("sentinel.verdicts", verdict.model_dump())

    asyncio.create_task(_write_audit(verdict))
    asyncio.create_task(_broadcast(verdict))
    _recent_verdicts.appendleft(verdict)
    _verdict_timestamps.append(time.perf_counter())
    return verdict


def _get_customer(account_id: str) -> CustomerInfo:
    """Stub — in production, look up from Postgres accounts table."""
    return CustomerInfo(
        account_id=account_id,
        phone="+977-9800000000",
        email=f"{account_id.lower()}@example.com",
    )


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """Deep liveness check — verifies Redis, Neo4j, and Postgres are reachable."""
    checks: dict[str, str] = {}
    ok = True

    # Redis
    try:
        import redis as _redis
        r = _redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        ok = False

    # Neo4j
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "sentinelpass"),
        ))
        driver.verify_connectivity()
        driver.close()
        checks["neo4j"] = "ok"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"
        # Neo4j degraded is non-fatal (GNN falls back gracefully)

    # Postgres
    try:
        async with await psycopg.AsyncConnection.connect(DB_URL, connect_timeout=2) as conn:
            await conn.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        ok = False

    status_code = 200 if ok else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"status": "ready" if ok else "degraded", "checks": checks},
        status_code=status_code,
    )


@app.post("/score")
async def score_direct(payload: dict) -> SynthesisVerdict:
    """Direct scoring endpoint (KAFKA_ENABLED=false fallback).
    Accepts any JSON shape — normalised via real_data_adapter.
    """
    from data.adapters.real_data_adapter import to_transaction_event
    tx = to_transaction_event(payload)
    return await process_transaction(tx)


@app.get("/verdicts/{tx_id}")
async def get_verdict(tx_id: str):
    for v in _recent_verdicts:
        if str(v.transaction_id) == tx_id:
            return v
    return {"error": "not_found"}


@app.get("/stats")
async def get_stats():
    verdicts = list(_recent_verdicts)
    if not verdicts:
        return {"total": 0, "allow": 0, "otp_interlock": 0, "block": 0,
                "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "tps": 0.0, "fraud_by_type": {}}
    total = len(verdicts)
    latencies = sorted(v.total_latency_ms for v in verdicts)

    def _pct(p: float) -> float:
        idx = min(int(total * p), total - 1)
        return latencies[idx]

    # TPS: count verdicts in the last 10 seconds
    now = time.perf_counter()
    tps_window = 10.0
    recent_count = sum(1 for t in _verdict_timestamps if now - t <= tps_window)
    tps = round(recent_count / tps_window, 1)

    fraud_by_type: dict[str, int] = {}
    for v in verdicts:
        if v.verdict in ("OTP_INTERLOCK", "BLOCK"):
            fraud_by_type[v.transaction_type] = fraud_by_type.get(v.transaction_type, 0) + 1

    return {
        "total": total,
        "allow": sum(1 for v in verdicts if v.verdict == "ALLOW"),
        "otp_interlock": sum(1 for v in verdicts if v.verdict == "OTP_INTERLOCK"),
        "block": sum(1 for v in verdicts if v.verdict == "BLOCK"),
        "p50_ms": round(_pct(0.50), 1),
        "p95_ms": round(_pct(0.95), 1),
        "p99_ms": round(_pct(0.99), 1),
        "tps": tps,
        "fraud_by_type": fraud_by_type,
    }


@app.get("/otp/pending")
async def otp_pending():
    return interlock.get_pending()


@app.post("/otp/confirm")
async def otp_confirm(tx_id: str, sms_code: str, email_code: str):
    result = interlock.confirm(tx_id, sms_code, email_code)
    log.info("otp.confirm", tx_id=tx_id, verdict=result.get("verdict"))
    return result


@app.post("/scenarios/run/{name}")
async def run_scenario(name: str):
    from tests.scenarios import _SCENARIOS
    fn = _SCENARIOS.get(name)
    if not fn:
        log.warning("scenario.unknown", name=name)
        return {"error": f"unknown scenario: {name}"}
    log.info("scenario.run", name=name)
    result = await asyncio.to_thread(fn)
    return result


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/verdicts")
async def ws_verdicts(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    log.debug("ws.connected", total_clients=len(_ws_clients))
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        _ws_clients.discard(ws)
        log.debug("ws.disconnected", total_clients=len(_ws_clients))


async def _broadcast(verdict: SynthesisVerdict) -> None:
    dead = set()
    payload = verdict.model_dump_json()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


# ---------------------------------------------------------------------------
# Kafka consumer loop
# ---------------------------------------------------------------------------

async def _kafka_consumer_loop() -> None:
    try:
        from kafka import KafkaConsumer
        from data.adapters.real_data_adapter import to_transaction_event
        consumer = KafkaConsumer(
            "sentinel.transactions",
            bootstrap_servers=KAFKA_SERVERS,
            value_deserializer=lambda b: json.loads(b.decode()),
            group_id="sentinel-orchestrator",
            auto_offset_reset="latest",
        )
        log.info("kafka.consumer.started")
        for msg in consumer:
            try:
                tx = to_transaction_event(msg.value)
                await process_transaction(tx)
            except Exception as e:
                log.error("kafka.consumer.error", error=str(e))
    except Exception as e:
        log.error("kafka.consumer.failed", error=str(e))


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

async def _ensure_audit_table() -> None:
    try:
        async with await psycopg.AsyncConnection.connect(DB_URL) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    transaction_id TEXT,
                    verdict TEXT,
                    composite_score REAL,
                    total_latency_ms REAL,
                    payload JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.commit()
        log.info("audit.table.ready")
    except Exception as e:
        log.warning("audit.db.unavailable", error=str(e))


async def _write_audit(verdict: SynthesisVerdict) -> None:
    try:
        async with await psycopg.AsyncConnection.connect(DB_URL) as conn:
            await conn.execute(
                "INSERT INTO audit_log (transaction_id, verdict, composite_score, total_latency_ms, payload) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    str(verdict.transaction_id), verdict.verdict,
                    verdict.composite_score, verdict.total_latency_ms,
                    json.dumps(verdict.model_dump(), default=str),
                ),
            )
            await conn.commit()
    except Exception:
        pass  # non-blocking — audit failure must not affect verdict
