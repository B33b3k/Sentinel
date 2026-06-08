# Data Schemas

The canonical **internal** schema is `orchestrator/schemas.py` (`TransactionEvent`,
`AgentScore`, `SynthesisVerdict`). Every agent consumes `TransactionEvent`. The
**source-of-truth for the real dataset** is `DATA_DESCRIPTION_Track_B.md` (GIBL
Track-B spec); this file records how that maps onto the internal model.

## Real → internal mapping

All real-data knowledge lives in two places:

- `data/adapters/real_data_adapter.py` — row-level normalisation (single mapping point).
- `data/loader.py` — `load_real_data()` reads + joins the real files (set `DATA_SOURCE=real`).

| Internal field (`TransactionEvent`) | Real source (DATA_DESCRIPTION §) | Notes |
|---|---|---|
| `transaction_id` (str) | `transactions_raw.txn_id` §3.1 | `TXN-YYYYMMDD-XXXXXXXX` — **string, not UUID** |
| `account_id` | `transactions_raw.account_id` §3.1 | `ACC-NNNNNNN` |
| `timestamp` (NPT-aware) | `transactions_raw.timestamp` §3.1 | Naive values treated as NPT (UTC+5:45) |
| `amount_npr` | `transactions_raw.amount_npr` §3.1 | |
| `currency` | `transactions_raw.currency` §3.1 | NPR/USD/GBP/INR/AED/QAR |
| `transaction_type` | `transactions_raw.txn_type` §3.1 | 8-value enum, adopted as-is |
| `counterparty_id` | `transactions_raw.counterparty_id` §3.1 | `MERCH-NNNN` / `ACC-NNNNNNN` |
| `device_id` | `transactions_raw.device_id` §3.1 | ~8% null |
| `ip_address` | `transactions_raw.ip_address` §3.1 | |
| `geo_lat` / `geo_lon` | `geo_events.latitude` / `.longitude` §3.4 | joined on `txn_id` |
| `geo_city` / `geo_district` | `geo_events.ip_city` §3.4 | district falls back to city |
| `account_home_district` | `customer_profiles.district` §3.2 | one of 10 districts |
| `account_age_days` | derived from `customer_profiles.customer_since` §3.2 | vs `REFERENCE_DATE` |
| `account_type` | derived from `customer_profiles.occupation_category` §3.2 | see map below |
| `extra` | velocity_snapshots / unmapped columns | preserved for later features |

## Enums

**`transaction_type`** (real §3.1, internal vocabulary):
`ESEWA_P2P`, `CARD_POS`, `ATM_WITHDRAWAL`, `SWIFT_OUTWARD`, `KHALTI_QR`, `RTGS`,
`MOBILE_TOPUP`, `UTILITY_BILL`. Legacy synthetic aliases normalise via `_TX_TYPE_MAP`
(`P2P→ESEWA_P2P`, `QR_ESEWA→KHALTI_QR`, `SWIFT_REMITTANCE→SWIFT_OUTWARD`, `ATM_POS→CARD_POS`).

For ML features the 8 types are collapsed into 4 model buckets
(`ml/training/featurize.py:TX_TYPE_BUCKET`) so `FEATURE_COLS` / LSTM `input_dim=13`
stay stable without retraining.

**`account_type`** (internal, derived from `occupation_category`):

| occupation_category | account_type |
|---|---|
| SALARIED, GOVERNMENT | SALARY |
| BUSINESS_OWNER, SELF_EMPLOYED | CURRENT |
| REMITTANCE_DEPENDENT | REMITTANCE |
| STUDENT | SAVINGS |

Drives cohort assignment in `ml/cohorts/assign.py`.

**Districts** (§3.2, 10 values): Kathmandu, Lalitpur, Bhaktapur, Pokhara, Butwal,
Biratnagar, Dharan, Hetauda, Chitwan, Nepalgunj.

**Verdict** (`SynthesisVerdict.verdict`): `ALLOW` / `OTP_INTERLOCK` / `BLOCK`.
> Note: the spec submission format §8.4 uses `ALLOW` / `OTP_ONLY` / `BLOCK`; a
> submission-generation step (mapping `OTP_INTERLOCK→OTP_ONLY`) is tracked separately.

## Closed

- Fraud-type labels: the synthetic generators now emit the §5 taxonomy
  (`SIM_SWAP`, `ACCOUNT_TAKEOVER`, `MONEY_MULE`, `SYNTHETIC_IDENTITY`,
  `C2_EXFILTRATION`, `SMURFING`) and `generate.py` writes `fraud_type` into
  `labels.parquet`. (Regeneration + retraining still needed to pick this up.)
- Submission CSV (§8.4): `orchestrator/submission.py` produces the required
  column set and maps `OTP_INTERLOCK→OTP_ONLY` (tests in `tests/test_submission.py`).
- Offline `featurize()` now localises naive timestamps as NPT, matching the live
  adapter (`tests/test_featurize_tz.py`).
- Batch scoring: `orchestrator/offline_scorer.py` derives agent scores from the
  precomputed velocity/geo/graph columns and fuses them with the live
  `SynthesisAgent`; `scripts/generate_submission.py` is the eval-day driver
  (`tests/test_offline_scorer.py`).
- Bonus artifacts (§8.2): `orchestrator/bonus.py` produces `community_detection.json`
  (COMM-042 ring), `otp_submission.csv` (sim-swap escalations) and `shap_values.csv`
  (additive top-5 attributions) (`tests/test_bonus.py`).

- Full §5 taxonomy coverage at scoring time: the offline scorer reads the raw eval
  columns directly, so `CARD_NOT_PRESENT` (is_international + CNP MCC),
  `SOCIAL_ENGINEERING` (MPIN/BIOMETRIC on anomalous transfer), `INSIDER_THREAT`
  (branch + large) and the §3.3 device signals (rooted + en_US, §4 pattern #4, 40×)
  now contribute. `predict_fraud_type()` fills the §8.4 `fraud_type_predicted` column.
- All 7 §4 hidden patterns fire at scoring time (structuring, fraud merchants, night
  ATO, rooted+en_US, dormancy break, recent beneficiary) or via the graph bonus
  artifact (COMM-042). See `docs/09-track-b-submission.md` §2.
- Evaluation harness: `orchestrator/metrics.py` + `scripts/evaluate.py` score the
  labelled `fraud_labels_train` split and report §8.1 metrics (AUROC, precision@5%FPR,
  recall, F1, FPR) vs the targets and the §8.3 rule-engine baseline
  (`tests/test_metrics.py`).

## Known gaps (not yet aligned)

- The offline scorer's per-agent formulas are heuristic decompositions of the
  precomputed signals — calibration against `fraud_labels_train` (and optional GBM
  blend per §8.3) is left as a tuning step once the real files are in hand.
- `FIRST_PARTY_FRAUD` is post-hoc (driven by `recovery_status` / `confirmed_by`
  dispute outcomes, §5) and is not detectable at transaction-scoring time.
- The synthetic generators still emit only the subset of columns the internal schema
  carries, so the device/auth/MCC-driven sub-types above light up on the real eval
  data but not on `data/seeds/` — synthetic parity would need generator + schema work.
