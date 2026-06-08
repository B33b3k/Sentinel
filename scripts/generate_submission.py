"""Eval-day driver — produce submission_[team].csv + all §8.2 bonus artifacts.

Reads the real Track-B files (DATA_DESCRIPTION_Track_B.md) from a directory, builds the
wide scoring frame (transactions_raw ⋈ geo_events ⋈ velocity_snapshots ⋈ graph features),
scores every row through the offline multi-agent pipeline, and writes:

  submission_[team].csv      (§8.4)
  community_detection.json   (§8.2 — COMM-042 ring)
  otp_submission.csv         (§8.2 — sim-swap escalations)
  shap_values.csv            (§8.2 — top-5 attributions per decision)

Usage:
  python3 scripts/generate_submission.py --data structured --team sentinel --out dist
"""
from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from orchestrator.bonus import write_community_detection, write_otp_submission, write_shap_values
from orchestrator.offline_scorer import predict_fraud_type, score_records
from orchestrator.submission import build_submission_df, row_from_verdict


def _read(base: pathlib.Path, name: str, **kw) -> pd.DataFrame | None:
    path = base / name
    if not path.exists():
        print(f"  ! {name} not found — skipping")
        return None
    return pd.read_csv(path, **kw)


def build_scoring_frame(base: pathlib.Path) -> pd.DataFrame:
    """Wide merge of the dictionary tables on txn_id / account_id for scoring."""
    txn = pd.read_csv(base / "transactions_raw.csv")

    geo = _read(base, "geo_events.csv")
    if geo is not None:
        keep = [c for c in (
            "txn_id", "impossible_travel", "is_tor", "is_datacenter", "is_vpn",
            "km_from_home_district", "prev_txn_km", "prev_txn_time_delta_min",
            "latitude", "longitude", "ip_city",
        ) if c in geo.columns]
        txn = txn.merge(geo[keep], on="txn_id", how="left")

    vel = _read(base, "velocity_snapshots.csv")
    if vel is not None:
        vel = vel.drop(columns=["account_id", "snapshot_time"], errors="ignore")
        txn = txn.merge(vel, on="txn_id", how="left")

    edges = _read(base, "account_graph_edges.csv")
    if edges is not None:
        keep = [c for c in ("txn_id", "within_24h_reciprocal", "is_first_transfer_to_target")
                if c in edges.columns]
        txn = txn.merge(edges[keep].drop_duplicates("txn_id"), on="txn_id", how="left")

    nodes = _read(base, "account_graph_nodes.csv")
    if nodes is not None:
        keep = [c for c in ("id", "degree_in", "degree_out", "is_fraud_seed") if c in nodes.columns]
        txn = txn.merge(nodes[keep].rename(columns={"id": "account_id"}), on="account_id", how="left")

    # device_fingerprints.json (§3.3) — device intelligence, joined on device_id.
    dev_path = base / "device_fingerprints.json"
    if "device_id" in txn.columns and dev_path.exists():
        dev = pd.read_json(dev_path)
        keep = [c for c in ("device_id", "is_rooted_or_jailbroken", "locale",
                            "is_shared_device", "num_accounts_seen_on_device") if c in dev.columns]
        txn = txn.merge(dev[keep], on="device_id", how="left")
    else:
        print("  ! device_fingerprints.json not found — skipping")

    return txn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="structured", help="dir with the real Track-B files")
    ap.add_argument("--team", default="sentinel")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args()

    base = pathlib.Path(args.data)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Building scoring frame from {base}/ ...")
    frame = build_scoring_frame(base)
    print(f"  → {len(frame):,} transactions")

    print("Scoring through the offline multi-agent pipeline ...")
    verdicts = score_records(frame.to_dict("records"))
    sub = build_submission_df(
        row_from_verdict(v, fraud_type_predicted=predict_fraud_type(v)) for v in verdicts
    )
    sub_path = out / f"submission_{args.team}.csv"
    sub.to_csv(sub_path, index=False)
    print(f"  → {sub_path} ({len(sub):,} rows)")
    print(sub["fraud_decision"].value_counts().to_string())

    # §8.2 bonus artifacts
    print("Writing bonus artifacts ...")
    edges = _read(base, "account_graph_edges.csv")
    nodes = _read(base, "account_graph_nodes.csv")
    if edges is not None:
        print(f"  → {write_community_detection(edges, out_dir=out, nodes=nodes)}")
    otp = _read(base, "otp_logs.csv")
    if otp is not None:
        print(f"  → {write_otp_submission(otp, out_dir=out)}")
    print(f"  → {write_shap_values(verdicts, out_dir=out)}")
    print("Done.")


if __name__ == "__main__":
    main()
