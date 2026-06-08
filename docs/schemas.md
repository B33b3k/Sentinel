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

## Known gaps (not yet aligned)

- Bonus artifacts (§8.2) are not yet produced: `community_detection.json` (COMM-042
  ring via graph), `otp_submission.csv` (sim_swap escalations), `shap_values.csv`.
- `submission.py` has no caller — a batch-scoring entry point that runs the eval set
  through the pipeline (or a model over the precomputed velocity/geo columns) and
  writes `submission_[team].csv` is still needed.
- Fraud sub-types that depend on columns the internal `TransactionEvent` does not yet
  carry (`channel`, `auth_method`, `is_international`, `merchant_category_code`):
  `CARD_NOT_PRESENT`, `SOCIAL_ENGINEERING`, `INSIDER_THREAT`, `FIRST_PARTY_FRAUD`.
