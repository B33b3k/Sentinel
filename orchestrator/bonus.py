"""Bonus-evidence artifacts (DATA_DESCRIPTION §8.2).

Each function operates on the dictionary-specified source tables and emits the exact
evidence file the rubric asks for:

  community_detection.json  ← account_graph_nodes/edges (§3.7/§3.8)  — COMM-042 ring
  otp_submission.csv        ← otp_logs (§3.6)                        — sim-swap escalations
  shap_values.csv           ← scored SynthesisVerdicts               — top-5 attributions/txn
"""
from __future__ import annotations

import json
import pathlib
from typing import Iterable

import pandas as pd

from agents.synthesis.agent import WEIGHTS_BY_TYPE, _FALLBACK_WEIGHTS
from orchestrator.schemas import SynthesisVerdict

# §3.7 — the collector account for the COMM-042 smurfing ring (degree_in ≈ 1890).
COMM042_COLLECTOR = "ACC-0011204"
COMM042_SIZE = 7  # §8.2: "all 7 member accounts"


# ── §8.2: COMM-042 smurfing community ───────────────────────────────────────

def detect_smurfing_community(
    edges: pd.DataFrame,
    collector: str = COMM042_COLLECTOR,
    size: int = COMM042_SIZE,
    nodes: pd.DataFrame | None = None,
) -> dict:
    """Find the accounts feeding the collector node (§3.8 directed money edges).

    Members are the direct in-neighbours of the collector, ranked by total NPR sent
    (the smurfs structuring funds into the collector), capped at `size`.
    """
    inbound = edges[edges["target"] == collector]
    ranked = (
        inbound.groupby("source")["amount_npr"].agg(["sum", "count"])
        .sort_values(["sum", "count"], ascending=False)
    )
    members = list(ranked.index[:size])

    fraud_seeds: list[str] = []
    if nodes is not None and "is_fraud_seed" in nodes.columns:
        seeds = nodes[nodes["is_fraud_seed"].astype(bool)]["id"]
        fraud_seeds = [m for m in members if m in set(seeds)]

    return {
        "community_id": "COMM-042",
        "collector_account": collector,
        "member_accounts": members,
        "total_members": len(members),
        "total_inflow_npr": round(float(inbound["amount_npr"].sum()), 2),
        "confirmed_fraud_seeds": fraud_seeds,
        "method": "directed in-neighbours of collector, ranked by total NPR sent (§3.8)",
    }


def write_community_detection(
    edges: pd.DataFrame, out_dir: pathlib.Path | str = ".", **kwargs
) -> pathlib.Path:
    result = detect_smurfing_community(edges, **kwargs)
    out = pathlib.Path(out_dir) / "community_detection.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    return out


# ── §8.2: OTP sim-swap escalations ──────────────────────────────────────────

OTP_SUBMISSION_COLUMNS = [
    "otp_event_id", "txn_id", "account_id", "escalation_reason", "action",
]


def otp_escalations(otp_logs: pd.DataFrame) -> pd.DataFrame:
    """Rows from otp_logs (§3.6) that must escalate as suspected SIM-swap.

    Per the interlock asymmetry (CLAUDE.md / agents/otp): SMS (channel_1) failing while
    EMAIL (channel_2) verifies is the sim-swap signal. We escalate when the dataset's
    `sim_swap_suspected` flag is set, OR channel_1 EXPIRED/FAILED while channel_2 VERIFIED,
    OR the row's own final_decision is already ESCALATED.
    """
    df = otp_logs
    ch1 = df.get("channel_1_status", pd.Series(index=df.index, dtype=object)).astype("string")
    ch2 = df.get("channel_2_status", pd.Series(index=df.index, dtype=object)).astype("string")
    suspected = df.get("sim_swap_suspected", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    final = df.get("final_decision", pd.Series(index=df.index, dtype=object)).astype("string")

    sms_fail_email_ok = ch1.isin(["EXPIRED", "FAILED"]) & ch2.eq("VERIFIED")
    mask = suspected | sms_fail_email_ok | final.eq("ESCALATED")

    reason = pd.Series("sim_swap_suspected", index=df.index)
    reason = reason.where(suspected, "sms_failed_email_verified")
    reason = reason.where(suspected | sms_fail_email_ok, "final_decision_escalated")

    out = pd.DataFrame({
        "otp_event_id": df.get("otp_event_id"),
        "txn_id": df.get("txn_id"),
        "account_id": df.get("account_id"),
        "escalation_reason": reason,
        "action": "ESCALATE",
    })[mask].reset_index(drop=True)
    return out[OTP_SUBMISSION_COLUMNS]


def write_otp_submission(otp_logs: pd.DataFrame, out_dir: pathlib.Path | str = ".") -> pathlib.Path:
    out = pathlib.Path(out_dir) / "otp_submission.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    otp_escalations(otp_logs).to_csv(out, index=False)
    return out


# ── §8.2: SHAP-style per-decision attributions ──────────────────────────────

SHAP_COLUMNS = ["txn_id", "rank", "feature", "shap_value"]


def explain_verdict(verdict: SynthesisVerdict, top_k: int = 5) -> list[dict]:
    """Additive per-decision attribution (SHAP/LIME-style).

    The composite is a weighted sum of agent scores, so each agent's weighted
    contribution (weight × score) is an exact additive attribution. We push it down to
    the feature level by splitting an agent's contribution across its reason_codes; the
    contributions sum to the composite score. Returns the top-`top_k` by magnitude.
    """
    weights = WEIGHTS_BY_TYPE.get(verdict.transaction_type, _FALLBACK_WEIGHTS)
    rows: list[dict] = []
    for s in verdict.agent_scores:
        contribution = weights.get(s.agent, 0.0) * s.score
        if contribution == 0.0:
            continue
        if s.reason_codes:
            share = contribution / len(s.reason_codes)
            for rc in s.reason_codes:
                rows.append({"feature": f"{s.agent}:{rc}", "shap_value": share})
        else:
            rows.append({"feature": f"{s.agent}:baseline", "shap_value": contribution})

    rows.sort(key=lambda r: abs(r["shap_value"]), reverse=True)
    return [
        {"txn_id": verdict.transaction_id, "rank": i + 1,
         "feature": r["feature"], "shap_value": round(r["shap_value"], 6)}
        for i, r in enumerate(rows[:top_k])
    ]


def build_shap_df(verdicts: Iterable[SynthesisVerdict], top_k: int = 5) -> pd.DataFrame:
    rows: list[dict] = []
    for v in verdicts:
        rows.extend(explain_verdict(v, top_k=top_k))
    df = pd.DataFrame(rows)
    return df[SHAP_COLUMNS] if not df.empty else pd.DataFrame(columns=SHAP_COLUMNS)


def write_shap_values(
    verdicts: Iterable[SynthesisVerdict], out_dir: pathlib.Path | str = ".", top_k: int = 5
) -> pathlib.Path:
    out = pathlib.Path(out_dir) / "shap_values.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_shap_df(verdicts, top_k=top_k).to_csv(out, index=False)
    return out
