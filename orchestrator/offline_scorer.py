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

# §4 hidden pattern #1 — structuring just below NRB reporting thresholds (2.1× lift):
# fraud amounts cluster within ±600 of these values.
_STRUCTURING_THRESHOLDS = (9999, 49999, 99999)
_STRUCTURING_BAND = 600.0


def _near_structuring_threshold(amount: float) -> bool:
    return any(abs(amount - t) <= _STRUCTURING_BAND for t in _STRUCTURING_THRESHOLDS)


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
    amount = _num(row, "amount_npr")
    structuring = _notna(row.get("amount_npr")) and _near_structuring_threshold(amount)
    if not _present(row, *cols) and not structuring:
        return None
    s, reasons = 0.0, []
    if structuring:
        s += 0.20  # §4 pattern #1: amount structured just below an NRB threshold
        reasons.append("structuring_amount")
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
    """geo_events §3.4 + device_fingerprints §3.3 — impossible_travel (#2 feature
    family), Tor/DC/VPN, distance, and device intelligence (rooted / locale mismatch)."""
    cols = ("impossible_travel", "is_tor", "is_datacenter", "is_vpn",
            "km_from_home_district", "prev_txn_km",
            "is_rooted_or_jailbroken", "locale", "is_shared_device",
            "num_accounts_seen_on_device")
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
    # Device intelligence (§3.3). Rooted device + en_US locale is §4 pattern #4 (40× lift);
    # the two contributions stack so that combination saturates the geo signal.
    rooted = _flag(row, "is_rooted_or_jailbroken")
    locale_mismatch = isinstance(row.get("locale"), str) and row["locale"] == "en_US"
    if rooted:
        s += 0.30
        reasons.append("rooted_device")
    if locale_mismatch:
        s += 0.25
        reasons.append("locale_mismatch")
    if rooted and locale_mismatch:
        s += 0.20
        reasons.append("rooted_locale_combo")
    if _flag(row, "is_shared_device") or _num(row, "num_accounts_seen_on_device") > 1:
        s += 0.20
        reasons.append("shared_device")
    return AgentScore(agent="geo", score=_clamp01(s), reason_codes=reasons, latency_ms=0.0)


# §5 CARD_NOT_PRESENT — international card fraud, usually these MCCs.
_CNP_MCC = frozenset({"4829", "7995", "5967"})


def score_behavior(row: dict) -> AgentScore | None:
    """Behavioural anomaly — night activity, new counterparty, amount/dormancy break,
    plus social-engineering / card-not-present / insider signals (§5 taxonomy)."""
    cols = ("night_flag", "new_counterparty_flag", "z_score_amount", "dormancy_break",
            "auth_method", "channel", "is_international", "merchant_category_code",
            "prev_txn_time_delta_min")
    if not _present(row, *cols):
        return None
    s, reasons = 0.0, []
    if _flag(row, "night_flag"):
        s += 0.25
        reasons.append("night_activity")  # §4 pattern #3: 73% of ATO at night
    new_cp = _flag(row, "new_counterparty_flag")
    if new_cp:
        s += 0.25
        reasons.append("new_counterparty")
    # §4 pattern #6: transfer to a beneficiary added <24h earlier (8.3× lift) —
    # approximated by a new counterparty within 24h of the previous transaction.
    if new_cp and 0 < _num(row, "prev_txn_time_delta_min") < 1440:
        s += 0.25
        reasons.append("recent_beneficiary")
    z = _num(row, "z_score_amount")
    if z >= 3.0:
        s += 0.30
        reasons.append("amount_anomaly")
    if _flag(row, "dormancy_break") and z >= 3.0:
        s += 0.30  # §4 pattern #5: dormancy break before large outward transfer (8×)
        reasons.append("dormancy_break_large")
    # §5 SOCIAL_ENGINEERING — customer deceived into authorising (legitimate auth on a
    # suspicious transfer): MPIN/BIOMETRIC together with an anomalous amount/new payee.
    auth = row.get("auth_method")
    if _notna(auth) and auth in {"MPIN", "BIOMETRIC"} and (z >= 3.0 or _flag(row, "new_counterparty_flag")):
        s += 0.30
        reasons.append("social_engineering_auth")
    # §5 CARD_NOT_PRESENT — cross-border card use on a CNP merchant category.
    mcc = row.get("merchant_category_code")
    if _flag(row, "is_international") and _notna(mcc) and str(mcc) in _CNP_MCC:
        s += 0.35
        reasons.append("card_not_present")
    # §5 INSIDER_THREAT — unusual large transfer on the branch channel.
    channel = row.get("channel")
    if _notna(channel) and channel == "BRANCH" and z >= 3.0:
        s += 0.30
        reasons.append("insider_branch_anomaly")
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


# ── Fraud-type prediction (§5 taxonomy, §8.4 optional column) ────────────────
# Reason-code → fraud_type, in priority order (most specific / highest-lift first).
_REASON_TO_TYPE: tuple[tuple[str, str], ...] = (
    ("fraud_merchant", "SMURFING"),
    ("smurfing_fanout", "SMURFING"),
    ("structuring_amount", "SMURFING"),
    ("mule_collector_shape", "MONEY_MULE"),
    ("layering_reciprocal", "MONEY_MULE"),
    ("card_not_present", "CARD_NOT_PRESENT"),
    ("social_engineering_auth", "SOCIAL_ENGINEERING"),
    ("insider_branch_anomaly", "INSIDER_THREAT"),
    ("datacenter_ip", "C2_EXFILTRATION"),
    ("velocity_burst_1m", "C2_EXFILTRATION"),
    ("dormancy_break_large", "SYNTHETIC_IDENTITY"),
    ("impossible_travel", "ACCOUNT_TAKEOVER"),
    ("rooted_locale_combo", "ACCOUNT_TAKEOVER"),
    ("night_activity", "ACCOUNT_TAKEOVER"),
)


def predict_fraud_type(verdict: SynthesisVerdict) -> str | None:
    """Best-guess §5 fraud_type from the fired reason codes, or None for ALLOW."""
    if verdict.verdict == "ALLOW":
        return None
    fired = {rc for s in verdict.agent_scores for rc in s.reason_codes}
    for reason, ftype in _REASON_TO_TYPE:
        if reason in fired:
            return ftype
    return None
