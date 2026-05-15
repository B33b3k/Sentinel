"""Synthesis Agent — context-aware weighted voting with verdict thresholds."""
from __future__ import annotations

import time

from orchestrator.schemas import AgentScore, SynthesisVerdict, TransactionEvent

# Weight matrix from concept paper Section 3.2.4
WEIGHTS_BY_TYPE: dict[str, dict[str, float]] = {
    "P2P":              {"velocity": 0.20, "geo": 0.30, "behavior": 0.30, "gnn": 0.20},
    "QR_ESEWA":         {"velocity": 0.35, "geo": 0.40, "behavior": 0.25, "gnn": 0.00},
    "SWIFT_REMITTANCE": {"velocity": 0.15, "geo": 0.25, "behavior": 0.20, "gnn": 0.40},
    "ATM_POS":          {"velocity": 0.30, "geo": 0.45, "behavior": 0.25, "gnn": 0.00},
}
_FALLBACK_WEIGHTS = {"velocity": 0.25, "geo": 0.35, "behavior": 0.25, "gnn": 0.15}

_ALLOW_THRESHOLD = 0.40
_BLOCK_THRESHOLD = 0.75


class SynthesisAgent:
    def synthesize(self, tx: TransactionEvent, scores: list[AgentScore]) -> SynthesisVerdict:
        t0 = time.perf_counter()

        weights = WEIGHTS_BY_TYPE.get(tx.transaction_type, _FALLBACK_WEIGHTS)

        # Index scores by agent name; missing agents → 0.5 neutral
        score_map: dict[str, float] = {}
        augmented_scores = list(scores)
        for agent_name in ("velocity", "geo", "behavior", "gnn"):
            match = next((s for s in scores if s.agent == agent_name), None)
            if match:
                score_map[agent_name] = match.score
            else:
                score_map[agent_name] = 0.5
                augmented_scores.append(AgentScore(
                    agent=agent_name,  # type: ignore[arg-type]
                    score=0.5,
                    reason_codes=["agent_unavailable"],
                    latency_ms=0.0,
                ))

        composite = sum(weights[a] * score_map[a] for a in weights)
        composite = round(min(1.0, max(0.0, composite)), 4)

        if composite < _ALLOW_THRESHOLD:
            verdict = "ALLOW"
        elif composite < _BLOCK_THRESHOLD:
            verdict = "OTP_INTERLOCK"
        else:
            verdict = "BLOCK"

        latency_ms = (time.perf_counter() - t0) * 1000
        return SynthesisVerdict(
            transaction_id=tx.transaction_id,
            composite_score=composite,
            verdict=verdict,
            agent_scores=augmented_scores,
            weights_used=weights,
            transaction_type=tx.transaction_type,
            total_latency_ms=round(latency_ms, 2),
        )
