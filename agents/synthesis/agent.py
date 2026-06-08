"""Synthesis Agent — context-aware weighted voting with verdict thresholds."""
from __future__ import annotations

import time

from orchestrator.schemas import AgentScore, SynthesisVerdict, TransactionEvent

# Context-aware weight matrix. Keyed on the real Track-B txn_type enum
# (DATA_DESCRIPTION §3.1); §6 motivates the per-type emphasis (e.g. eSewa P2P and
# offshore SWIFT/RTGS lean on the graph signal, QR/POS lean on geo/velocity).
# The legacy 4 keys are retained for backward compatibility (demo scenarios/tests).
WEIGHTS_BY_TYPE: dict[str, dict[str, float]] = {
    # --- real Track-B types ---
    "ESEWA_P2P":        {"velocity": 0.20, "geo": 0.15, "behavior": 0.25, "gnn": 0.40},
    "KHALTI_QR":        {"velocity": 0.35, "geo": 0.35, "behavior": 0.25, "gnn": 0.05},
    "CARD_POS":         {"velocity": 0.25, "geo": 0.40, "behavior": 0.30, "gnn": 0.05},
    "ATM_WITHDRAWAL":   {"velocity": 0.30, "geo": 0.45, "behavior": 0.20, "gnn": 0.05},
    "SWIFT_OUTWARD":    {"velocity": 0.15, "geo": 0.20, "behavior": 0.20, "gnn": 0.45},
    "RTGS":             {"velocity": 0.15, "geo": 0.15, "behavior": 0.25, "gnn": 0.45},
    "MOBILE_TOPUP":     {"velocity": 0.40, "geo": 0.25, "behavior": 0.30, "gnn": 0.05},
    "UTILITY_BILL":     {"velocity": 0.30, "geo": 0.25, "behavior": 0.40, "gnn": 0.05},
    # --- legacy types (concept-paper Section 3.2.4) ---
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

        # Calculate total latency: sum of all agent latencies + synthesis overhead
        agent_latency_sum = sum(s.latency_ms for s in augmented_scores)
        synthesis_overhead = (time.perf_counter() - t0) * 1000
        total_latency = agent_latency_sum + synthesis_overhead
        
        return SynthesisVerdict(
            transaction_id=tx.transaction_id,
            composite_score=composite,
            verdict=verdict,
            agent_scores=augmented_scores,
            weights_used=weights,
            transaction_type=tx.transaction_type,
            total_latency_ms=round(total_latency, 2),
        )
