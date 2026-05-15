"""GNN Agent — Cypher mule-ring detection with Redis score cache.

Neo4j connection is lazy: the agent starts and scores transactions even if
Neo4j is unavailable. Scores fall back to 0.5 (neutral) with a reason code
until the connection is established.
"""
from __future__ import annotations

import os
import time

import redis

from orchestrator.schemas import AgentScore, TransactionEvent

_MULE_QUERY = """
MATCH (sources:Account)-[t1:TRANSFERRED]->(mule:Account)-[t2:TRANSFERRED]->(dest:Account)
WHERE t1.timestamp > datetime() - duration('P1D')
  AND t2.timestamp > t1.timestamp
  AND t2.timestamp < t1.timestamp + duration('PT2H')
WITH mule, dest,
     count(DISTINCT sources) AS source_count,
     sum(t1.amount) AS inflow,
     sum(t2.amount) AS outflow
WHERE source_count >= 3 AND outflow >= 0.7 * inflow
RETURN mule.id AS mule_id, dest.id AS dest_id, source_count, inflow, outflow
"""

_CACHE_TTL = 3600  # 1 hour


class GNNAgent:
    AGENT_NAME = "gnn"

    def __init__(
        self,
        neo4j_uri: str | None = None,
        neo4j_auth: tuple | None = None,
        redis_url: str = "redis://localhost:6379/0",
    ) -> None:
        self._uri = neo4j_uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._auth = neo4j_auth or (
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "sentinelpass"),
        )
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._driver = None  # lazy — connected on first use

    def _get_driver(self):
        """Return a live driver, or None if Neo4j is unreachable."""
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(self._uri, auth=self._auth)
            driver.verify_connectivity()
            self._driver = driver
            return self._driver
        except Exception:
            return None

    def score(self, tx: TransactionEvent) -> AgentScore:
        t0 = time.perf_counter()
        cache_key = f"gnn:{tx.account_id}"

        cached = self._r.get(cache_key)
        if cached is not None:
            return AgentScore(
                agent="gnn",
                score=round(float(cached), 4),
                reason_codes=["gnn:cache_hit"],
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            )

        score, reason = self._query_neo4j(tx.account_id)
        self._r.setex(cache_key, _CACHE_TTL, str(score))

        return AgentScore(
            agent="gnn",
            score=round(score, 4),
            reason_codes=reason,
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    def _query_neo4j(self, account_id: str) -> tuple[float, list[str]]:
        driver = self._get_driver()
        if driver is None:
            return 0.5, ["gnn:neo4j_unavailable"]
        try:
            with driver.session() as session:
                result = session.run(_MULE_QUERY)
                flagged_ids: set[str] = set()
                for r in result:
                    flagged_ids.add(r["mule_id"])
                    flagged_ids.add(r["dest_id"])
            if account_id in flagged_ids:
                return 0.92, ["mule_ring_detected"]
            return 0.05, ["no_mule_pattern"]
        except Exception as e:
            # Close the broken driver before clearing the reference
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None  # reset so next call retries
            return 0.5, [f"gnn_error:{type(e).__name__}"]

    def close(self) -> None:
        if self._driver:
            self._driver.close()
