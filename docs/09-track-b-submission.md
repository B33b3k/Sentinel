# 09 — Track-B Data Alignment & Eval-Day Submission

This doc explains how SENTINEL consumes the **real GIBL Track-B dataset**
(`DATA_DESCRIPTION_Track_B.md` is the source of truth) and how to produce the
competition submission + bonus artifacts on evaluation day.

> The real `structured/*.csv` files are only available **on hackathon day**. Everything
> below is built against the data dictionary and verified on dictionary-shaped fixtures,
> so it is ready to run the moment the files land.

---

## 1. Where real-data knowledge lives

All knowledge of the real format is confined to two places — nothing downstream changes:

| Concern | File |
|---|---|
| Row-level normalisation (column + enum mapping) | `data/adapters/real_data_adapter.py` |
| Reading + joining the real tables | `data/loader.py` (`load_real_data`, `DATA_SOURCE=real`) |

Everything else consumes the internal `TransactionEvent` (`orchestrator/schemas.py`).
The full real→internal field/enum mapping table is in [`schemas.md`](./schemas.md).

Key alignment points:
- `transaction_id` is a **string** (`TXN-YYYYMMDD-XXXXXXXX`), not a UUID.
- Timestamps are **NPT (UTC+5:45)**; naive values are localised to NPT everywhere
  (live adapter and offline `featurize()`), so `night_flag`/hour features are correct.
- `txn_type` uses the 8-value §3.1 enum; `account_type` is derived from
  `occupation_category`; districts are the 10 §3.2 values.

---

## 2. Scoring strategy — multi-agent over precomputed signals

SENTINEL is a **multi-agent** system, not a monolithic model (see
[`decisions.md`](./decisions.md) D1/D6/D7). The eval dataset ships the expensive
per-transaction signals **precomputed** — `velocity_snapshots` (§3.5), `geo_events`
(§3.4) — plus the money-movement graph (§3.7/§3.8) and device fingerprints (§3.3).

So `orchestrator/offline_scorer.py` derives each agent's score directly from those
columns and fuses them with the **same context-aware `SynthesisAgent` used online** —
no Redis/Neo4j required. `fraud_probability = composite_score`. Agents whose entire
input-column family is absent return `None`, so synthesis imputes a neutral `0.5`
(mirroring the live timeout behaviour) rather than biasing toward ALLOW.

### §4 hidden-pattern coverage

| # | Pattern | Where it fires | Lift |
|---|---|---|---|
| 1 | Structuring ±600 of NRB thresholds | velocity → `structuring_amount` | 2.1× |
| 2 | Fraud merchants (MERCH-8812/9041/7712) | gnn → `fraud_merchant` | 227× |
| 3 | Night-time account takeover | behavior → `night_activity` | 4.2× |
| 4 | Rooted device + `en_US` locale | geo → `rooted_locale_combo` | 40× |
| 5 | Dormancy break before large transfer | behavior → `dormancy_break_large` | 8× |
| 6 | New beneficiary within 24h | behavior → `recent_beneficiary` | 8.3× |
| 7 | COMM-042 smurfing ring | `bonus.detect_smurfing_community` | — |

The §5 fraud taxonomy is covered at scoring time except `SIM_SWAP` (handled via the OTP
artifact) and `FIRST_PARTY_FRAUD` (post-hoc, dispute-driven). `predict_fraud_type()`
fills the optional §8.4 `fraud_type_predicted` column from the fired reason codes.

---

## 3. Eval-day workflow

```bash
# 0. Place the real files under ./structured/ (transactions_raw.csv, geo_events.csv,
#    velocity_snapshots.csv, account_graph_{nodes,edges}.csv, otp_logs.csv,
#    device_fingerprints.json, fraud_labels_train.csv)

# 1. Check standing vs the §8.1 targets and §8.3 rule-engine baseline (uses train labels)
python3 scripts/evaluate.py --data structured                 # --sample 100000 to go fast

# 2. Produce the submission + all §8.2 bonus artifacts into ./dist/
python3 scripts/generate_submission.py --data structured --team sentinel --out dist
```

### Outputs (`dist/`)

| File | Spec | Producer |
|---|---|---|
| `submission_sentinel.csv` | §8.4 | `orchestrator/submission.py` |
| `community_detection.json` | §8.2 (+5%) | `orchestrator/bonus.py` |
| `otp_submission.csv` | §8.2 (+5%) | `orchestrator/bonus.py` |
| `shap_values.csv` | §8.2 (+3%) | `orchestrator/bonus.py` |

`submission.csv` columns (§8.4): `txn_id, fraud_probability, fraud_decision`
(`ALLOW`/`OTP_ONLY`/`BLOCK`), `fraud_type_predicted`, `agent_scores_json`, `latency_ms`.

---

## 4. Calibration (the one real-data step)

The per-agent score formulas are principled heuristic decompositions of the precomputed
signals. Once the real labels are in hand, calibrate thresholds/weights against
`fraud_labels_train` via `scripts/evaluate.py`; if AUROC trails the 0.93 target, a
LightGBM/XGBoost blend (§8.3 reference: 0.984) can be layered in behind the same
`fraud_probability` output without changing the submission contract.

---

## 5. Tests

| Area | Test |
|---|---|
| Adapter mapping / NPT | `tests/adapters/test_real_data_adapter.py` |
| Offline scorer + patterns + fraud_type | `tests/test_offline_scorer.py` |
| Bonus artifacts | `tests/test_bonus.py` |
| Submission contract | `tests/test_submission.py` |
| §8.1 metrics | `tests/test_metrics.py` |
| featurize NPT | `tests/test_featurize_tz.py` |

```bash
python3 -m pytest tests/ -q --ignore=tests/smoke --ignore=tests/load --ignore=tests/scenarios
```
