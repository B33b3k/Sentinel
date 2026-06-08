"""Offline batch scorer — turns the real Track-B eval files into agent scores.

Strategy (see docs/decisions.md D1/D6/D7 + DATA_DESCRIPTION_Track_B.md): SENTINEL is
a *multi-agent* system, not a monolithic model. The eval dataset already ships the
expensive per-transaction signals precomputed — `velocity_snapshots` (§3.5) and
`geo_events` (§3.4) — plus the money-movement graph (§3.7/§3.8). So instead of
replaying every row through the live, stateful agents (which need Redis/Neo4j), each
agent's score is derived here from those precomputed columns, then fused by the same
context-aware `SynthesisAgent` used online. fraud_probability = composite_score.

Every score function reads dictionary column names verbatim and returns `None` when
none of its input columns are present, so the synthesis layer imputes a neutral 0.5
(mirroring the live timeout behaviour) rather than biasing toward ALLOW.
"""
from __future__ import annotations

from typing import Any, Iterable

from agents.synthesis.agent import SynthesisAgent
from data.adapters.real_data_adapter import to_transaction_event
from orchestrator.schemas import AgentScore, SynthesisVerdict

# §4 hidden pattern #2 — three merchant IDs over-represented in fraud chains (227× lift).
FRAUD_MERCHANTS = frozenset({"MERCH-8812", "MERCH-9041", "MERCH-7712"})


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _present(row: dict, *cols: str) -> bool:
    """True if at least one column is present and not null."""
    return any(c in row and _notna(row[c]) for c in cols)


def _notna(v: Any) -> bool:
    return v is not None and v == v  # NaN != NaN


def _num(row: dict, col: str, default: float = 0.0) -> float:
    v = row.get(col)
    return float(v) if _notna(v) else default


def _flag(row: dict, col: str) -> bool:
    v = row.get(col)
    if not _notna(v):
        return False
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes"}
    return bool(v)


# ── Per-agent scoring from precomputed columns ──────────────────────────────

def score_velocity(row: dict) -> AgentScore | None:
    """velocity_snapshots §3.5 — z_score_amount (the #1 feature), bursts, fan-out."""
    cols = ("z_score_amount", "txn_count_1m", "unique_counterparties_1h", "dormancy_break")
    if not _present(row, *cols):
        return None
    s, reasons = 0.0, []
    z = _num(row, "z_score_amount")
    if z >= 3.5:
        s += _clamp01((z - 1.0) / 4.0) * 0.6 + 0.1
        reasons.append("z_score_amount_high")
    elif z >= 1.0:
        s += _clamp01((z - 1.0) / 4.0) * 0.6
    if _num(row, "txn_count_1m") >= 3:
        s += 0.30
        reasons.append("velocity_burst_1m")
    if _num(row, "unique_counterparties_1h") >= 4:
        s += 0.30
        reasons.append("smurfing_fanout")
    if _flag(row, "dormancy_break"):
        s += 0.20
        reasons.append("dormancy_break")
    return AgentScore(agent="velocity", score=_clamp01(s), reason_codes=reasons, latency_ms=0.0)


def score_geo(row: dict) -> AgentScore | None:
    """geo_events §3.4 — impossible_travel (#2 feature family), Tor/DC/VPN, distance."""
    cols = ("impossible_travel", "is_tor", "is_datacenter", "is_vpn",
            "km_from_home_district", "prev_txn_km")
    if not _present(row, *cols):
        return None
    s, reasons = 0.0, []
    if _flag(row, "impossible_travel"):
        s += 0.60
        reasons.append("impossible_travel")
    if _flag(row, "is_tor"):
        s += 0.30
        reasons.append("tor_exit_node")
    if _flag(row, "is_datacenter"):
        s += 0.25
        reasons.append("datacenter_ip")
    if _flag(row, "is_vpn"):
        s += 0.20
        reasons.append("vpn_detected")
    s += _clamp01(_num(row, "km_from_home_district") / 1000.0) * 0.30
    s += _clamp01(_num(row, "prev_txn_km") / 2000.0) * 0.30
    return AgentScore(agent="geo", score=_clamp01(s), reason_codes=reasons, latency_ms=0.0)


def score_behavior(row: dict) -> AgentScore | None:
    """Behavioural anomaly — night activity, new counterparty, amount/dormancy break."""
    cols = ("night_flag", "new_counterparty_flag", "z_score_amount", "dormancy_break")
    if not _present(row, *cols):
        return None
    s, reasons = 0.0, []
    if _flag(row, "night_flag"):
        s += 0.25
        reasons.append("night_activity")  # §4 pattern #3: 73% of ATO at night
    if _flag(row, "new_counterparty_flag"):
        s += 0.25
        reasons.append("new_counterparty")
    z = _num(row, "z_score_amount")
    if z >= 3.0:
        s += 0.30
        reasons.append("amount_anomaly")
    if _flag(row, "dormancy_break") and z >= 3.0:
        s += 0.30  # §4 pattern #5: dormancy break before large outward transfer (8×)
        reasons.append("dormancy_break_large")
    return AgentScore(agent="behavior", score=_clamp01(s), reason_codes=reasons, latency_ms=0.0)


def score_gnn(row: dict) -> AgentScore | None:
    """Graph signal §3.7/§3.8 + §4 merchant/mule patterns."""
    cols = ("counterparty_id", "is_fraud_seed", "within_24h_reciprocal",
            "is_first_transfer_to_target", "degree_in", "degree_out")
    if not _present(row, *cols):
        return None
    s, reasons = 0.0, []
    cp = row.get("counterparty_id")
    if _notna(cp) and cp in FRAUD_MERCHANTS:
        s += 0.80
        reasons.append("fraud_merchant")  # §4 pattern #2 (227× lift)
    if _flag(row, "is_fraud_seed"):
        s += 0.70
        reasons.append("fraud_seed_node")
    if _flag(row, "within_24h_reciprocal"):
        s += 0.40
        reasons.append("layering_reciprocal")
    if _flag(row, "is_first_transfer_to_target"):
        s += 0.25
        reasons.append("first_transfer_to_target")
    # Mule shape: high in-degree, near-zero out-degree (§3.7).
    if _num(row, "degree_in") >= 500 and _num(row, "degree_out") <= 5:
        s += 0.50
        reasons.append("mule_collector_shape")
    return AgentScore(agent="gnn", score=_clamp01(s), reason_codes=reasons, latency_ms=0.0)


_SCORERS = (score_velocity, score_geo, score_behavior, score_gnn)


def score_row(row: dict, synth: SynthesisAgent | None = None) -> SynthesisVerdict:
    """Score one merged eval row → SynthesisVerdict (fraud_probability = composite)."""
    synth = synth or SynthesisAgent()
    tx = to_transaction_event(row)
    scores = [s for fn in _SCORERS if (s := fn(row)) is not None]
    return synth.synthesize(tx, scores)


def score_records(rows: Iterable[dict]) -> list[SynthesisVerdict]:
    """Score many merged eval rows. Pass DataFrame.to_dict('records')."""
    synth = SynthesisAgent()
    return [score_row(row, synth) for row in rows]
