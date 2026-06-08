# GIBL AI/ML Hackathon 2026 — Track B
## Agentic Fraud Detection Framework
# Data Description & Technical Reference Manual

---

> **Version:** 1.0
> **Classification:** Participant-Accessible (fraud_labels_eval_HIDDEN.csv withheld)
> **Domain:** Transaction Fraud Detection | Behavioural Analytics | Graph Analysis

---

## Table of Contents

1. [Dataset Overview](#1-dataset-overview)
2. [Entity Relationship & Data Model](#2-entity-relationship--data-model)
3. [Table-by-Table Data Dictionary](#3-table-by-table-data-dictionary)
   - 3.1 transactions_raw
   - 3.2 customer_profiles
   - 3.3 device_fingerprints
   - 3.4 geo_events
   - 3.5 velocity_snapshots
   - 3.6 otp_logs
   - 3.7 account_graph_nodes
   - 3.8 account_graph_edges
   - 3.9 fraud_labels_train / fraud_labels_eval_HIDDEN
   - 3.10 rule_engine_baseline_predictions
   - 3.11 model_verdicts_sample
4. [Noise & Data Quality Reference](#4-noise--data-quality-reference)
5. [Fraud Type Taxonomy](#5-fraud-type-taxonomy)
6. [Nepal-Specific Banking Context](#6-nepal-specific-banking-context)
7. [Data Formats & Conventions](#7-data-formats--conventions)
8. [Evaluation Metrics Reference](#8-evaluation-metrics-reference)

---

## 1. Dataset Overview

### 1.1 Purpose

This dataset simulates the real-time transaction monitoring environment of a Nepali
commercial bank processing approximately 480,000 digital transactions daily across
eSewa, Khalti, card POS, ATM, SWIFT, and internal RTGS channels.

The bank's existing fraud detection system is a legacy rule engine with 25 static rules.
It produces a **false positive rate of ~14%** (blocking legitimate customers) and a
**recall of only 62%** (missing 38% of actual fraud). The goal of this track is to build
a multi-agent ML system that replaces it.

The dataset supports the following ML/AI tasks:

| Task | Primary Tables Used |
|---|---|
| **Fraud Detection (primary)** | transactions_raw, velocity_snapshots, geo_events, fraud_labels_train |
| **Behavioral Modeling** | transactions_raw, customer_profiles (LSTM per-account baseline) |
| **Graph Fraud Detection** | account_graph_nodes, account_graph_edges |
| **OTP Interlock Logic** | otp_logs, transactions_raw |
| **Anomaly Detection** | velocity_snapshots (z_score_amount, txn_count_1m) |
| **Device Intelligence** | device_fingerprints, geo_events |
| **LLM / Explainability** | model_verdicts_sample (agent reasoning chains) |

### 1.2 Scale Summary

| File | Rows | Format | Size (raw) |
|---|---|---|---|
| transactions_raw.csv | 2,000,000 | CSV | 334 MB |
| customer_profiles.csv | 50,000 | CSV | 6.9 MB |
| device_fingerprints.json | 200,000 | JSON | 79 MB |
| geo_events.csv | 2,000,000 | CSV | 331 MB |
| velocity_snapshots.csv | 2,000,000 | CSV | 279 MB |
| otp_logs.csv | ~43,000 | CSV | 8.6 MB |
| account_graph_nodes.csv | 50,001 | CSV | 3.5 MB |
| account_graph_edges.csv | 500,000 | CSV | 51 MB |
| fraud_labels_train.csv | 400,000 | CSV | 16 MB |
| fraud_labels_eval_HIDDEN.csv | 1,600,000 | CSV | 63 MB |
| rule_engine_baseline_predictions.csv | 2,000,000 | CSV | 84 MB |
| model_verdicts_sample.json | 100,000 | JSON | 59 MB |

### 1.3 Key Design Decisions

- **Not all transactions have all signals.** `device_id` is null for ~8% of web/branch
  transactions. `merchant_category_code` is null for ~4% of QR payments. The `notes`
  field is null for ~78% of transactions. This sparsity is intentional and realistic.
- **Labels are partially released.** 20% of labels (400,000 rows) are in
  `fraud_labels_train.csv`. The remaining 80% are in `fraud_labels_eval_HIDDEN.csv`
  and must not be distributed to participants before evaluation day.
- **Fraud rate is 1.80% overall** (36,000 / 2,000,000). The hidden evaluation set has
  an adversarially elevated rate of ~3.2% to test model robustness.
- **Seven hidden patterns** are embedded in the data. Discovering them earns bonus marks
  (see §4 and §8).
- **The baseline to beat** is the legacy rule engine (AUROC 0.71, F1 0.54, FPR 14%).

---

## 2. Entity Relationship & Data Model

```
customer_profiles (1)
    │
    ├──── (1:0..N) transactions_raw         [all transacting accounts]
    │         ├── (1:1) geo_events          [one geo record per transaction]
    │         ├── (1:1) velocity_snapshots  [one velocity snapshot per transaction]
    │         ├── (1:0..1) otp_logs         [only ~2.2% of transactions trigger OTP]
    │         ├── (1:1) fraud_labels_train  [20% of rows have labels released]
    │         └── (1:1) rule_engine_baseline_predictions
    │
    ├──── (1:0..N) account_graph_nodes      [one node per account]
    │         └── (1:0..N) account_graph_edges [directed money movement edges]
    │
    └──── (1:0..N) device_fingerprints      [device used for transaction]
```

**Primary transaction key:** `txn_id` (format: `TXN-YYYYMMDD-XXXXXXXX`)

**Primary account key:** `account_id` (format: `ACC-NNNNNNN`)

**Foreign keys:**
- All transaction-level tables reference `txn_id` from `transactions_raw`
- `geo_events.account_id`, `velocity_snapshots.account_id` reference `customer_profiles.account_id`
- `device_fingerprints.device_id` referenced by `transactions_raw.device_id`
- `account_graph_edges.source` and `.target` reference `account_graph_nodes.id`

---

## 3. Table-by-Table Data Dictionary

---

### 3.1 `transactions_raw.csv`

**Description:** The primary dataset. Every row is one bank transaction. This is the
starting point for all feature engineering. Covers all digital channels including mobile
wallets (eSewa/Khalti), card POS, ATM withdrawals, SWIFT international transfers, RTGS,
mobile top-ups, and utility bill payments over an 18-month period (January 2025–June 2026).

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `txn_id` | STRING | No | `TXN-YYYYMMDD-XXXXXXXX` | **Primary key.** Unique transaction identifier. Format: `TXN-` + date + `-` + 8-character hex. Never reused. |
| `timestamp` | DATETIME | No | `YYYY-MM-DD HH:MM:SS.mmm` | Transaction initiation time in UTC+5:45 (Nepal Standard Time). **Noise:** ~0.9% of ATM records are in UTC instead of NPT. |
| `account_id` | STRING | No | `ACC-NNNNNNN` | Source account identifier. FK → customer_profiles.account_id. |
| `counterparty_id` | STRING | No | `MERCH-NNNN` or `ACC-NNNNNNN` | Destination account or merchant ID. Three specific merchant IDs (MERCH-8812, MERCH-9041, MERCH-7712) are embedded fraud signal merchants. |
| `txn_type` | ENUM | No | See enum below | Transaction channel/product type. Determines applicable NRB rules, velocity thresholds, and synthesis agent weights. |
| `amount_npr` | FLOAT | No | Positive float | Transaction amount in Nepalese Rupees. **Noise:** ~12% of records show 2 decimal places vs 4 (channel-dependent precision inconsistency). **Hidden pattern:** fraud transactions cluster at NPR 9,999 / 49,999 / 99,999 (structuring just below NRB reporting thresholds). |
| `currency` | STRING | No | `NPR`, `USD`, `GBP`, `INR`, `AED`, `QAR` | ISO 4217 currency code of the original transaction. Domestic transactions are always `NPR`. |
| `channel` | ENUM | No | `MOBILE_APP`, `WEB`, `ATM`, `BRANCH`, `API` | Origination channel of the transaction request. |
| `device_id` | STRING | Yes | `DEV-XXXXXX` | Device fingerprint reference. **~8.1% null** for web browser sessions and branch transactions. FK → device_fingerprints.device_id. |
| `ip_address` | STRING | No | IPv4 address string | Originating IP address. **Noise:** ~0.2% are malformed (`127.0.0.1`, `0.0.0.0`, `10.0.0.1`) — proxy/VPN artifacts. Do not geolocate these. |
| `merchant_category_code` | STRING | Yes | 4-digit ISO 18245 code | Merchant category code. **~4.2% null** for QR payments and mobile top-ups that bypass MCC assignment. Common codes: 5411 (Grocery), 5812 (Restaurant), 6011 (ATM), 4814 (Telecom), 4829 (Wire Transfer). |
| `terminal_id` | STRING | Yes | `POS-XXX-NNNN` or `ATM-XXX-NN` | POS terminal or ATM machine identifier. Null for mobile/web channels. |
| `session_id` | STRING | Yes | `SESS-XXXXXX` | Application or web session identifier. Null for ATM transactions. |
| `auth_method` | ENUM | No | `MPIN`, `BIOMETRIC`, `OTP_SMS`, `OTP_EMAIL`, `CARD_PIN` | Authentication method used for the transaction. Note: `BIOMETRIC` or `OTP_SMS` on a fraud transaction indicates social engineering (customer was deceived into authorizing). |
| `response_code` | STRING | No | `00`, `05`, `51`, `57` | Issuer response code. `00` = approved, `05` = declined (do not honour), `51` = insufficient funds, `57` = transaction not permitted. **Noise:** ~0.4% of transactions have `response_code = 00` but are subsequently confirmed fraud (delayed identification). Do not filter on this field. |
| `processing_time_ms` | INT | No | 80–750 | Backend processing latency in milliseconds. Unusually low values (<100ms) on burst sequences may indicate automated/scripted attacks. |
| `is_international` | BOOL | No | `True`, `False` | True for cross-border transactions (SWIFT international transfers or international card usage). |
| `fx_rate` | FLOAT | Yes | Positive float or NULL | Exchange rate applied at transaction time. **Null for all domestic NPR transactions** (~94% of dataset). |
| `notes` | STRING | Yes | Free text or NULL | Sender-entered memo. **~78% null.** Do not use as a primary feature without NLP preprocessing. Common values: `rent payment`, `grocery`, `loan emi`, `school fees`. |

**txn_type valid values:**
`ESEWA_P2P`, `CARD_POS`, `ATM_WITHDRAWAL`, `SWIFT_OUTWARD`, `KHALTI_QR`, `RTGS`,
`MOBILE_TOPUP`, `UTILITY_BILL`

**txn_type distribution (approximate):**
ESEWA_P2P ~25%, CARD_POS ~20%, ATM_WITHDRAWAL ~15%, KHALTI_QR ~15%, MOBILE_TOPUP ~10%,
UTILITY_BILL ~9%, RTGS ~3%, SWIFT_OUTWARD ~3%

---

### 3.2 `customer_profiles.csv`

**Description:** Master record for each account holder. One row per account. Contains
demographic information, channel preferences, risk classification, and product linkages.
This is the root table — all other tables link to it via `account_id`.

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `account_id` | STRING | No | `ACC-NNNNNNN` | **Primary key.** Unique account identifier. Never reused. |
| `customer_since` | STRING | No | `YYYY-MM-DD` | Account opening date (Gregorian). Accounts opened before 2015 tend to have richer behavioral baselines. |
| `age_group` | ENUM | No | `18-24`, `25-34`, `35-44`, `45-54`, `55+` | Age bracket. Exact date of birth is not included to protect synthetic privacy. |
| `district` | STRING | No | One of 10 districts | Home district of registered address. Values: Kathmandu, Lalitpur, Bhaktapur, Pokhara, Butwal, Biratnagar, Dharan, Hetauda, Chitwan, Nepalgunj. |
| `province` | STRING | No | Province name | Province derived from district. Values: Bagmati, Gandaki, Lumbini, Koshi. |
| `occupation_category` | ENUM | No | See enum below | Primary occupation. Used to contextualize expected transaction patterns. |
| `monthly_income_band_npr` | ENUM | No | `<15K`, `15K-30K`, `30K-75K`, `75K-200K`, `200K+` | Income bracket declared at KYC. Not the model-estimated income. |
| `kyc_tier` | ENUM | No | `BASIC`, `STANDARD`, `ENHANCED` | KYC verification level. Determines transaction limits per NRB Unified Directives 2080. |
| `risk_tier` | ENUM | No | `LOW`, `MEDIUM`, `HIGH`, `WATCHLIST` | Bank-assigned risk category. Distribution: LOW 55%, MEDIUM 30%, HIGH 12%, WATCHLIST 3%. |
| `avg_monthly_txn_count` | INT | No | 5–250 | Historical monthly average transaction count (30-day rolling). |
| `avg_monthly_txn_value_npr` | FLOAT | No | Positive float | Historical average total monthly spend in NPR. |
| `primary_channel` | ENUM | No | `MOBILE_APP`, `WEB`, `BRANCH`, `ATM` | Most frequently used channel. |
| `international_txn_history` | BOOL | No | `True`, `False` | True if the account has previously completed at least one international transfer. ~18% of accounts. |
| `has_linked_esewa` | BOOL | No | `True`, `False` | eSewa mobile wallet linked to this account. ~65% of accounts. |
| `has_linked_khalti` | BOOL | No | `True`, `False` | Khalti wallet linked. ~40% of accounts. |
| `num_beneficiaries_registered` | INT | No | 0–50 | Number of pre-registered payees. **Hidden pattern:** transfers to beneficiaries added within 24 hours of the transaction are 8.3× more likely to be fraudulent. |
| `last_profile_update` | STRING | No | `YYYY-MM-DD` | Date of most recent KYC or profile update. |
| `is_dormant` | BOOL | No | `True`, `False` | True if no transactions in the last 6 months. ~6% of accounts. **Signal:** dormant accounts that suddenly transact large amounts are elevated risk. |
| `churn_risk_score` | FLOAT | No | 0.0–1.0 | Propensity to close account, generated from engagement signals. Not a fraud signal but useful for false-positive cost weighting. |

**occupation_category valid values:**
`SALARIED`, `SELF_EMPLOYED`, `STUDENT`, `REMITTANCE_DEPENDENT`, `BUSINESS_OWNER`, `GOVERNMENT`

---

### 3.3 `device_fingerprints.json`

**Description:** JSON array. One object per registered device. Device risk signals are
among the highest-precision fraud indicators in the dataset. A rooted device with a
locale mismatch (en_US on a Nepali IP) has an empirically measured 40× fraud lift.

```json
{
  "device_id": "DEV-7F3A21",
  "first_seen": "2024-09-12T08:33:21Z",
  "last_seen": "2026-05-31T02:14:07Z",
  "device_type": "MOBILE",
  "os": "Android 14",
  "app_version": "3.8.1",
  "locale": "ne_NP",
  "timezone": "Asia/Kathmandu",
  "is_rooted_or_jailbroken": false,
  "vpn_detected": false,
  "tor_exit_node": false,
  "biometric_enrolled": true,
  "num_accounts_seen_on_device": 1,
  "is_shared_device": false,
  "risk_signals": []
}
```

| Field | Type | Nullable | Description |
|---|---|---|---|
| `device_id` | STRING | No | **Primary key.** Matches `device_id` in transactions_raw. |
| `first_seen` | STRING | No | ISO 8601 UTC datetime of first transaction from this device. |
| `last_seen` | STRING | No | ISO 8601 UTC datetime of most recent transaction. |
| `device_type` | ENUM | No | `MOBILE`, `DESKTOP`, `TABLET`. ~80% MOBILE. |
| `os` | STRING | No | Operating system and version string. |
| `app_version` | STRING | No | Banking app version. Old versions (<3.5.0) lack biometric hardening. |
| `locale` | STRING | No | Device locale setting. **Signal:** `en_US` on a Nepali IP address is a strong fraud indicator. Legitimate Nepali users almost always have `ne_NP`. |
| `timezone` | STRING | No | Device timezone. Mismatch with the transaction IP's resolved country = suspicious. |
| `is_rooted_or_jailbroken` | BOOL | No | Root or jailbreak detected. Strongly correlated with fraud in this dataset. |
| `vpn_detected` | BOOL | No | VPN or proxy was active at the time of the transaction. |
| `tor_exit_node` | BOOL | No | IP is a known Tor exit node at transaction time. |
| `biometric_enrolled` | BOOL | No | Biometric authentication configured in app. |
| `num_accounts_seen_on_device` | INT | No | Distinct accounts that have transacted from this device. `>1` suggests a shared or mule device. Fraud devices average 3.2 accounts. |
| `is_shared_device` | BOOL | No | True if more than one account has used this device. |
| `risk_signals` | ARRAY | No | List of active risk flags. Values: `NEW_DEVICE`, `ROOTED`, `VPN_ACTIVE`, `MULTI_ACCOUNT`, `TIMEZONE_MISMATCH`. Empty array for clean devices. |

**Loading note:** This is a JSON file, not CSV.

```python
import json, pandas as pd
with open("structured/device_fingerprints.json") as f:
    devices = json.load(f)
df_devices = pd.DataFrame(devices)
```

---

### 3.4 `geo_events.csv`

**Description:** One geolocation record per transaction. Produced by IP resolution at
transaction time. `impossible_travel` and `prev_txn_km` are the top-ranked features in
all trained baseline models. The `is_vpn`, `is_tor`, and `is_datacenter` flags come
from IP reputation databases, not self-reported.

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `txn_id` | STRING | No | FK to transactions_raw | Transaction reference. |
| `account_id` | STRING | No | FK to customer_profiles | Account reference. |
| `timestamp` | DATETIME | No | `YYYY-MM-DD HH:MM:SS.mmm` | Equals `transactions_raw.timestamp`. |
| `ip_address` | STRING | No | IPv4 string | Raw IP as submitted by the client. |
| `ip_country` | STRING | No | Country name | Country resolved from IP geolocation. |
| `ip_city` | STRING | No | City name | City resolved from IP geolocation. |
| `ip_isp` | STRING | No | ISP name | Internet Service Provider. Nepali ISPs: Nepal Telecom, WorldLink, Subisu, Vianet. Foreign ISPs on Nepali accounts = suspicious. |
| `ip_asn` | STRING | No | `AS` + number | Autonomous System Number. Known Tor/VPN ASNs are flagged via `is_tor`/`is_vpn`. |
| `latitude` | FLOAT | No | Decimal degrees | Approximate latitude from IP geolocation. Accuracy: ±2–20 km. |
| `longitude` | FLOAT | No | Decimal degrees | Approximate longitude from IP geolocation. |
| `accuracy_km` | FLOAT | No | Positive float | Radius of geolocation uncertainty in kilometres. |
| `is_vpn` | BOOL | No | `True`, `False` | IP is a known VPN exit node per IP reputation database. |
| `is_tor` | BOOL | No | `True`, `False` | IP is a known Tor exit node. ~1% of fraud transactions. |
| `is_datacenter` | BOOL | No | `True`, `False` | IP is from a datacenter range (non-residential). Indicates automated/scripted transaction origin. |
| `velocity_flag` | BOOL | No | `True`, `False` | Transaction velocity from this IP exceeds configured thresholds. |
| `km_from_home_district` | FLOAT | No | Positive float | Distance (km) from account's registered district centroid to transaction IP location. |
| `prev_txn_km` | FLOAT | No | Positive float | Distance (km) from previous transaction's geo-resolved location. **The #2 model feature.** For impossible travel scenarios this can be 4,000–8,000 km. |
| `prev_txn_time_delta_min` | FLOAT | No | Positive float | Minutes elapsed since the previous transaction from this account. **The #1 model feature (time_delta).** |
| `impossible_travel` | BOOL | No | `True`, `False` | True when `prev_txn_km / prev_txn_time_delta_min` implies travel speed exceeding 900 km/h (faster than a commercial aircraft). |

---

### 3.5 `velocity_snapshots.csv`

**Description:** Pre-computed sliding-window velocity features, one row per transaction.
These are computed at the moment of the transaction using only historical data (no
lookahead). `z_score_amount` is the single most important feature across all trained
baseline models. Participants may recompute or extend these windows.

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `txn_id` | STRING | No | FK to transactions_raw | Transaction reference. |
| `account_id` | STRING | No | FK to customer_profiles | Account reference. |
| `snapshot_time` | DATETIME | No | `YYYY-MM-DD HH:MM:SS.mmm` | Equals transaction timestamp. |
| `txn_count_1m` | INT | No | 0–20 | Transactions from this account in the last 1 minute. Values ≥3 at 02:00–04:00 NPT are strongly predictive of fraud bursts. |
| `txn_count_5m` | INT | No | 0–30 | Transactions from this account in the last 5 minutes. |
| `txn_count_15m` | INT | No | 0–50 | Transactions from this account in the last 15 minutes. |
| `txn_count_1h` | INT | No | 0–100 | Transactions from this account in the last 1 hour. |
| `txn_count_24h` | INT | No | 0–300 | Transactions from this account in the last 24 hours. |
| `txn_count_7d` | INT | No | 0–600 | Transactions from this account in the last 7 days. |
| `total_amount_1h_npr` | FLOAT | No | Positive float | Total outgoing amount (NPR) in the last 1 hour. |
| `total_amount_24h_npr` | FLOAT | No | Positive float | Total outgoing amount (NPR) in the last 24 hours. |
| `unique_counterparties_1h` | INT | No | 0–20 | Distinct recipients in the last 1 hour. Values ≥4 to previously-unseen recipients within 1 hour is a smurfing indicator. |
| `unique_counterparties_24h` | INT | No | 0–50 | Distinct recipients in the last 24 hours. |
| `new_counterparty_flag` | BOOL | No | `True`, `False` | True if this recipient has never been transacted with before by this account. |
| `max_single_txn_24h_npr` | FLOAT | No | Positive float | Largest single transaction amount in the last 24 hours. |
| `avg_txn_amount_30d_npr` | FLOAT | No | Positive float | 30-day rolling average transaction amount for this account. |
| `std_txn_amount_30d_npr` | FLOAT | No | Positive float | 30-day rolling standard deviation of transaction amounts. |
| `z_score_amount` | FLOAT | No | Float | `(amount_npr − avg_txn_amount_30d_npr) / std_txn_amount_30d_npr`. **The #1 model feature.** Values ≥3.5 indicate the transaction is unusually large relative to the account's history. |
| `dormancy_break` | BOOL | No | `True`, `False` | True if this is the first transaction after 14+ days of zero activity. |
| `weekend_flag` | BOOL | No | `True`, `False` | Transaction occurred on Saturday or Sunday. |
| `night_flag` | BOOL | No | `True`, `False` | Transaction occurred between 22:00 and 05:00 Nepal Standard Time. **Hidden pattern:** 73% of ACCOUNT_TAKEOVER fraud events have `night_flag = True`. |

---

### 3.6 `otp_logs.csv`

**Description:** One row per OTP challenge event. Only ~2.2% of all transactions trigger
an OTP (high-risk fraud detections + random sample of legitimate high-value transactions).
The dual-path interlock requires both SMS and EMAIL OTP to be verified. If either channel
fails, the transaction is blocked or escalated.

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `otp_event_id` | STRING | No | `OTP-XXXXXX` | Unique OTP event identifier. |
| `txn_id` | STRING | No | FK to transactions_raw | The transaction that triggered the OTP challenge. |
| `account_id` | STRING | No | FK to customer_profiles | Account being challenged. |
| `trigger_reason` | STRING | No | See enum below | Why the OTP was triggered. |
| `otp_channel_1` | ENUM | No | `SMS`, `EMAIL`, `PUSH` | First OTP delivery channel. Always `SMS` in this dataset. |
| `otp_channel_2` | ENUM | Yes | `SMS`, `EMAIL`, `PUSH`, NULL | Second channel for dual-path interlock. Always `EMAIL` when present. Null for single-channel challenge. |
| `channel_1_sent_at` | DATETIME | No | `YYYY-MM-DD HH:MM:SS.mmm` | When channel 1 OTP was dispatched. |
| `channel_2_sent_at` | DATETIME | Yes | `YYYY-MM-DD HH:MM:SS.mmm` or NULL | When channel 2 OTP was dispatched. Null if single-channel. |
| `channel_1_verified_at` | DATETIME | Yes | `YYYY-MM-DD HH:MM:SS.mmm` or NULL | When channel 1 OTP entry was confirmed. Null if not verified. |
| `channel_2_verified_at` | DATETIME | Yes | `YYYY-MM-DD HH:MM:SS.mmm` or NULL | When channel 2 OTP entry was confirmed. Null if not verified. |
| `channel_1_status` | ENUM | No | `VERIFIED`, `EXPIRED`, `FAILED`, `PENDING` | Resolution status of channel 1 challenge. |
| `channel_2_status` | ENUM | No | `VERIFIED`, `EXPIRED`, `FAILED`, `PENDING` | Resolution status of channel 2 challenge. |
| `final_decision` | ENUM | No | `ALLOWED`, `BLOCKED`, `ESCALATED` | `ALLOWED` = both channels verified. `BLOCKED` = at least one failed. `ESCALATED` = SIM-swap suspected or multi-failure pattern. |
| `resolution_time_ms` | INT | No | Positive integer | Total elapsed time from OTP dispatch to final decision, in milliseconds. |
| `attempt_count_ch1` | INT | No | 0–5 | Number of OTP entry attempts on channel 1. Values ≥3 may indicate brute-force. |
| `attempt_count_ch2` | INT | No | 0–5 | Number of OTP entry attempts on channel 2. |
| `sim_swap_suspected` | BOOL | No | `True`, `False` | True if the SMS was delivered to a SIM inconsistent with the account's registered phone history. The primary indicator of SIM-swap fraud type. |

**trigger_reason valid values:**
`HIGH_AMOUNT_NEW_COUNTERPARTY`, `IMPOSSIBLE_TRAVEL_DETECTED`, `GEO_ANOMALY`,
`VELOCITY_SPIKE`, `NEW_DEVICE`, `DORMANCY_BREAK`

---

### 3.7 `account_graph_nodes.csv`

**Description:** One row per account node in the money-movement graph. Covers the
90-day window of transactions. Use with `account_graph_edges.csv` for Graph Neural
Network (GNN) training. High `degree_in` + low `degree_out` with near-zero net balance
is the money mule pattern (account absorbs funds and passes them on).

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `id` | STRING | No | `ACC-NNNNNNN` | **Primary key.** Account identifier. FK → customer_profiles.account_id. |
| `type` | ENUM | No | `PERSONAL`, `BUSINESS` | Account type classification. |
| `risk_tier` | ENUM | No | `LOW`, `MEDIUM`, `HIGH`, `WATCHLIST` | Bank risk classification (same as customer_profiles.risk_tier). |
| `kyc_tier` | ENUM | No | `BASIC`, `STANDARD`, `ENHANCED` | KYC verification level. |
| `degree_in` | INT | No | 0–2000 | Number of incoming edges (transfers received) in the 90-day window. The collector node `ACC-0011204` has degree_in of 1,890. |
| `degree_out` | INT | No | 0–500 | Number of outgoing edges (transfers sent) in the 90-day window. |
| `total_received_npr` | FLOAT | No | Positive float | Total NPR received across all incoming edges in the window. |
| `total_sent_npr` | FLOAT | No | Positive float | Total NPR sent across all outgoing edges in the window. |
| `is_fraud_seed` | BOOL | No | `True`, `False` | True if this account is a confirmed fraud node (collector account or known mule). Used for GNN label propagation. |

**Special node:** `ACC-0011204` is the collector account for the COMM-042 smurfing ring.
It has `is_fraud_seed = True`, `risk_tier = WATCHLIST`, `degree_in = 1890`.

---

### 3.8 `account_graph_edges.csv`

**Description:** Directed edges representing money movement between accounts. Each row is
one transaction edge. Use alongside `account_graph_nodes.csv` for GNN training.
`is_first_transfer_to_target` is an important fraud signal — first-time transfers to
previously-unseen recipients carry 8× higher fraud probability in this dataset.

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `source` | STRING | No | `ACC-NNNNNNN` | Sending account ID. FK → account_graph_nodes.id. |
| `target` | STRING | No | `ACC-NNNNNNN` or `MERCH-NNNN` | Receiving account or merchant ID. |
| `txn_id` | STRING | No | FK to transactions_raw | Transaction reference. |
| `amount_npr` | FLOAT | No | Positive float | Transaction amount in NPR. |
| `timestamp` | DATETIME | No | `YYYY-MM-DD HH:MM:SS.mmm` | Transaction timestamp. |
| `txn_type` | ENUM | No | Same values as transactions_raw.txn_type | Transaction type. |
| `edge_weight` | FLOAT | No | `1.0` | Edge weight for GNN. Default 1.0 per transaction. Participants may experiment with amount-normalized weights. |
| `is_first_transfer_to_target` | BOOL | No | `True`, `False` | True if this is the first ever transfer from this source account to this target. |
| `within_24h_reciprocal` | BOOL | No | `True`, `False` | True if the target sent money back to the source within 24 hours of this transaction (layering pattern — common in money laundering). |

**Loading note for GNN training:**

```python
import pandas as pd
nodes = pd.read_csv("structured/account_graph_nodes.csv")
edges = pd.read_csv("structured/account_graph_edges.csv")

# PyTorch Geometric edge_index format
src = edges["source"].map(dict(zip(nodes["id"], nodes.index))).values
tgt = edges["target"].map(dict(zip(nodes["id"], nodes.index))).fillna(-1).values
```

---

### 3.9 `fraud_labels_train.csv` / `fraud_labels_eval_HIDDEN.csv`

**Description:** Ground truth fraud labels. `fraud_labels_train.csv` (20% of total rows,
400,000 records) is released to participants for model training and validation.
`fraud_labels_eval_HIDDEN.csv` (80% of total rows, 1,600,000 records) is withheld and
used only by organizers for final scoring.

**Important:** The evaluation set has an adversarially elevated fraud rate of ~3.2%
(vs 1.8% in training) and includes harder-to-detect fraud sub-types.

| Column | Type | Nullable | Valid Values / Format | Description |
|---|---|---|---|---|
| `txn_id` | STRING | No | FK to transactions_raw | Transaction reference. |
| `is_fraud` | BOOL | No | `True`, `False` | **Ground truth label.** True = confirmed fraud. Overall rate: 1.80% (36,000 / 2,000,000). |
| `fraud_type` | ENUM | Yes | See §5 taxonomy | Fraud sub-category. Null when `is_fraud = False`. |
| `fraud_confidence` | FLOAT | Yes | 0.70–1.00 or NULL | Annotator confidence score. Null when `is_fraud = False`. All released labels have confidence ≥ 0.70. |
| `confirmed_by` | ENUM | Yes | `SOC_ANALYST`, `RULE_ENGINE`, `ML_CONFIRMED`, `CUSTOMER_DISPUTE` | Source of fraud confirmation. Null when `is_fraud = False`. |
| `fraud_date_confirmed` | STRING | Yes | `YYYY-MM-DD` or NULL | Date fraud was confirmed. May be days or weeks after the original transaction. |
| `financial_loss_npr` | FLOAT | Yes | 0.0 or positive float | NPR amount lost. 0 if transaction was blocked before settlement. |
| `recovery_status` | ENUM | Yes | `NONE`, `PARTIAL`, `FULL` or NULL | Whether the lost amount was recovered. Null when `is_fraud = False`. |

**Class imbalance note:** With 1.8% fraud rate, a naive classifier predicting all
`is_fraud = False` achieves 98.2% accuracy but 0% recall. Use
`scale_pos_weight = (len - n_fraud) / n_fraud` in XGBoost or `class_weight = 'balanced'`
in scikit-learn. All evaluation metrics weight the fraud class appropriately.

---

### 3.10 `rule_engine_baseline_predictions.csv`

**Description:** Outputs of the legacy rule engine (25 static rules) on all 2,000,000
transactions. This is the system participants must outperform. AUROC 0.71, FPR 14%.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `txn_id` | STRING | No | FK to transactions_raw |
| `baseline_decision` | ENUM | No | `FLAG` or `ALLOW`. `FLAG` = rule engine suspects fraud |
| `rule_triggered` | STRING | No | Which rule fired: `AMOUNT_THRESHOLD`, `VELOCITY_RULE`, `GEO_BLACKLIST`, `NONE` |
| `confidence` | FLOAT | No | Rule engine confidence 0.5–0.9. All rules are binary so this is limited. |

---

### 3.11 `model_verdicts_sample.json`

**Description:** Pre-computed 5-agent pipeline verdicts for 100,000 transactions.
Each record shows the individual sub-scores from all five agents and the synthesis
agent's weighted decision. Participants should use this as a reference for the expected
output format and should build systems that outperform these scores.

```json
{
  "txn_id": "TXN-20260531-A9F3C1AB",
  "evaluated_at": "2026-05-31T02:14:08Z",
  "agent_verdicts": {
    "velocity_agent": {
      "score": 0.78,
      "flag": "HIGH",
      "inference_ms": 42
    },
    "geo_agent": {
      "score": 0.31,
      "flag": "LOW",
      "inference_ms": 38
    },
    "behavior_agent": {
      "score": 0.84,
      "flag": "HIGH",
      "inference_ms": 187
    },
    "graph_agent": {
      "score": 0.91,
      "flag": "CRITICAL",
      "inference_ms": 224
    },
    "synthesis_agent": {
      "final_score": 0.88,
      "final_decision": "BLOCK_AND_OTP",
      "weights_applied": {
        "velocity": 0.20,
        "geo": 0.10,
        "behavior": 0.30,
        "graph": 0.40
      },
      "total_pipeline_ms": 552
    }
  },
  "baseline_rule_engine_decision": "ALLOW",
  "baseline_correct": false
}
```

**Key JSON fields:**

| Field | Type | Description |
|---|---|---|
| `txn_id` | STRING | FK to transactions_raw |
| `evaluated_at` | DATETIME | Verdict timestamp (ISO 8601 UTC) |
| `agent_verdicts.*.score` | FLOAT (0–1) | Sub-score from each agent |
| `agent_verdicts.*.flag` | ENUM | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `agent_verdicts.*.inference_ms` | INT | Agent-specific latency |
| `synthesis_agent.final_score` | FLOAT (0–1) | Weighted ensemble score |
| `synthesis_agent.final_decision` | ENUM | `ALLOW`, `OTP_ONLY`, `BLOCK_AND_OTP` |
| `synthesis_agent.weights_applied` | JSON | Weights used (vary by txn_type) |
| `synthesis_agent.total_pipeline_ms` | INT | End-to-end pipeline latency |
| `baseline_rule_engine_decision` | ENUM | `FLAG` or `ALLOW` from the legacy system |
| `baseline_correct` | BOOL | Whether baseline matched ground truth |

---

## 4. Noise & Data Quality Reference

Noise is embedded intentionally to simulate realistic enterprise data quality issues.
The table below describes each issue, its rate, and how to handle it.

| Issue | Rate | Affected File | Recommended Handling |
|---|---|---|---|
| NULL `merchant_category_code` | 4.2% | transactions_raw | Impute from `txn_type` median or treat as category `UNKNOWN` |
| NULL `device_id` | 8.1% | transactions_raw | Flag as missing feature; do not drop rows — many are legitimate web sessions |
| Empty `notes` field | ~78% | transactions_raw | Exclude from baseline features; NLP optional |
| Malformed IP addresses | 0.2% | transactions_raw | Treat `127.0.0.1`, `0.0.0.0`, `10.*` as missing — do not geolocate |
| Mixed timestamp timezone | 0.9% | transactions_raw | Some ATM records are in UTC. Normalise all to UTC+5:45 before deriving `night_flag` |
| Amount precision mismatch | ~12% | transactions_raw | Channel-dependent (2dp vs 4dp). Normalise to 4dp before feature engineering |
| Response code 00 on later-disputed transaction | 0.4% | transactions_raw | Do not filter on `response_code`. Fraud can be confirmed weeks after approval |
| Duplicate transaction (replay simulation) | 0.3% | transactions_raw | Same `account_id` + `amount_npr` + timestamp within ±5 seconds. Deduplicate if needed |
| Impossible travel events | ~0.55% of fraud | geo_events | Do not drop — these are real fraud signals. `impossible_travel = True` is a feature |

### Hidden Patterns (for advanced teams and judges)

These patterns are intentionally embedded. Discovering them earns bonus evaluation marks.

| # | Pattern | Signal Column | Lift |
|---|---|---|---|
| 1 | Round-number structuring at NPR 9,999 / 49,999 / 99,999 | `amount_npr` within ±600 of threshold | 2.1× |
| 2 | Three merchant IDs over-represented in fraud chains | `counterparty_id` in {MERCH-8812, MERCH-9041, MERCH-7712} | 227× |
| 3 | 73% of ACCOUNT_TAKEOVER events between 01:00–04:00 NPT | `night_flag` + hour derived from `timestamp` | 4.2× |
| 4 | Rooted device + `en_US` locale on Nepali IP | Join `device_fingerprints` on `txn_id` | 40× |
| 5 | Dormancy break before large outward transfer | `dormancy_break = True` + `z_score_amount > 3` | 8× |
| 6 | Transfer to beneficiary added <24h earlier | `new_counterparty_flag` + `prev_txn_time_delta_min < 1440` | 8.3× |
| 7 | COMM-042 smurfing community (7 accounts → ACC-0011204) | GNN on `account_graph_edges` | n/a |

---

## 5. Fraud Type Taxonomy

`fraud_type` in `fraud_labels_train.csv` uses the following 10 categories. Each type
has distinct feature signatures. The distribution is approximately equal across types
but slightly over-indexed on ACCOUNT_TAKEOVER and SMURFING (18% and 14% respectively).

| fraud_type | Description | Key feature indicators |
|---|---|---|
| `ACCOUNT_TAKEOVER` | Credential compromise via phishing or malware. Attacker logs in from new device/location and drains account. 73% occur at night (01:00–04:00 NPT). | `night_flag`, `is_vpn`, `new_counterparty_flag`, new `device_id` |
| `CARD_NOT_PRESENT` | Online card fraud without physical card. Card details obtained from data breach or skimmer. Usually international MCC. | `is_international`, MCC 4829/7995/5967 |
| `SIM_SWAP` | Mobile number ported to attacker SIM. Attacker bypasses SMS OTP. `channel_1_status = EXPIRED` with `sim_swap_suspected = True`. | `otp_logs.sim_swap_suspected`, `channel_1_status = EXPIRED` |
| `SOCIAL_ENGINEERING` | Customer deceived into authorizing the transfer themselves. Auth shows legitimate session — the customer complied. | `auth_method = MPIN` or `BIOMETRIC` on suspicious amount/counterparty |
| `SMURFING` | Structuring: multiple transfers just below NRB reporting thresholds (NPR 9,999 / 49,999 / 99,999). | `amount_npr` near threshold, `unique_counterparties_1h ≥ 3` |
| `MONEY_MULE` | Account used as a pass-through for laundering. High `degree_in` + `degree_out` with near-zero net balance. | `is_fraud_seed` in graph, `account_graph_nodes.degree_in` |
| `SYNTHETIC_IDENTITY` | Fake KYC documents used to open account. Normal activity for months, then sudden large outward transfer. | `dormancy_break`, `kyc_tier = BASIC`, `z_score_amount > 5` |
| `INSIDER_THREAT` | Bank staff-assisted fraud. Unusual large transfers on branch channel. | `channel = BRANCH`, high `amount_npr`, off-hours |
| `C2_EXFILTRATION` | Malware-driven automated transfers to C2-controlled accounts. Regular small bursts to Eastern European IPs. | `txn_count_1m ≥ 3`, `is_datacenter = True`, Eastern European `ip_country` |
| `FIRST_PARTY_FRAUD` | Account holder falsely claims unauthorized transaction to receive chargeback. Auth shows legitimate session. | `recovery_status = FULL` + `confirmed_by = CUSTOMER_DISPUTE` |

---

## 6. Nepal-Specific Banking Context

**eSewa (eSewa Fonepay)**
Nepal's largest mobile payment platform. Supports bill payments, merchant QR, P2P
transfers, and remittance receipt. ~65% of dataset accounts have eSewa linked.
`txn_type = ESEWA_P2P` is a high-value P2P transfer via eSewa. The synthesis agent
weights the graph signal highest for this type (40% vs 20% for velocity) because
smurfing rings predominantly use eSewa P2P.

**Khalti**
Second-largest Nepali mobile wallet. Popular with younger users. QR-code based payments
(`txn_type = KHALTI_QR`) are typically low-value (NPR 50–2,000) and have a different
fraud profile than eSewa P2P.

**SWIFT (Society for Worldwide Interbank Financial Telecommunication)**
International wire transfer network. `txn_type = SWIFT_OUTWARD` in this dataset
represents outward international transfers. These carry elevated AML risk and trigger
NRB reporting requirements above certain thresholds. The C2_EXFILTRATION fraud type
predominantly uses SWIFT_OUTWARD to move funds offshore.

**RTGS (Real-Time Gross Settlement)**
Nepal Rastra Bank's high-value domestic interbank transfer system. Used for large
corporate payments (NPR 200,000+). Appears in dataset at ~3% of transaction volume.

**NRB Unified Directives 2080**
Nepal Rastra Bank's primary regulatory framework governing all commercial bank
operations. Key rules modeled in this dataset:

- `NRB-KYC-001`: KYC tier determines per-transaction limits
- `NRB-AML-004`: AML screening required for all transactions above NPR 100,000
- `NRB-CTR-008`: Currency Transaction Report mandatory for cash transactions > NPR 1,000,000
- `NRB-STR-009`: Suspicious Transaction Report mandatory when fraud is suspected

**Nepal Rastra Bank (NRB)**
Nepal's central bank and primary regulator of all financial institutions.
All fraud detection systems must produce audit trails compliant with NRB requirements.

**Bikram Sambat (BS) Calendar**
Nepal's official calendar. Approximately 56–57 years ahead of Gregorian (AD).
Example: AD 2026 ≈ BS 2083. Timestamps in this dataset are all Gregorian.

---

## 7. Data Formats & Conventions

| Aspect | Convention | Example |
|---|---|---|
| Transaction ID | `TXN-YYYYMMDD-XXXXXXXX` | `TXN-20260531-A9F3C1AB` |
| Account ID | `ACC-NNNNNNN` | `ACC-0048293` |
| Device ID | `DEV-XXXXXX` | `DEV-7F3A21` |
| OTP Event ID | `OTP-XXXXXX` | `OTP-A1B2C3` |
| Timestamps | `YYYY-MM-DD HH:MM:SS.mmm` | `2026-05-31 02:14:07.481` |
| Dates | ISO 8601 `YYYY-MM-DD` | `2026-05-31` |
| JSON datetimes | ISO 8601 with Z suffix | `2026-05-31T02:14:07Z` |
| Currency | NPR (Nepalese Rupees) | `85000.00` |
| Boolean | `True` / `False` | `True` |
| NULL handling | Empty cell in CSV | — |
| Noise columns | Embedded (no prefix) | See §4 for locations |

### Loading the JSON files

```python
import json, pandas as pd

# Device fingerprints (200,000 records)
with open("structured/device_fingerprints.json") as f:
    devices = json.load(f)
df_devices = pd.DataFrame(devices)

# Model verdicts (100,000 records) — nested JSON
with open("structured/model_verdicts_sample.json") as f:
    verdicts = json.load(f)
# Flatten agent scores
records = []
for v in verdicts:
    row = {"txn_id": v["txn_id"]}
    for agent, vals in v["agent_verdicts"].items():
        for k, val in vals.items():
            row[f"{agent}_{k}"] = val
    records.append(row)
df_verdicts = pd.DataFrame(records)
```

### Joining the main tables

```python
import pandas as pd

txn   = pd.read_csv("structured/transactions_raw.csv")
prof  = pd.read_csv("structured/customer_profiles.csv")
geo   = pd.read_csv("structured/geo_events.csv")
vel   = pd.read_csv("structured/velocity_snapshots.csv")
labels = pd.read_csv("structured/fraud_labels_train.csv")

# Full feature matrix for modelling
df = (txn
      .merge(vel.drop(columns=["account_id","snapshot_time"]), on="txn_id", how="left")
      .merge(geo.drop(columns=["account_id","timestamp"]), on="txn_id", how="left")
      .merge(labels[["txn_id","is_fraud"]], on="txn_id", how="inner"))  # labelled rows only
```

### Handling imbalanced classes

```python
from sklearn.utils.class_weight import compute_sample_weight
import lightgbm as lgb

# Option 1: class_weight
model = lgb.LGBMClassifier(class_weight="balanced")

# Option 2: scale_pos_weight (XGBoost)
n_neg = (y_train == 0).sum()
n_pos = (y_train == 1).sum()
model = xgb.XGBClassifier(scale_pos_weight=n_neg/n_pos)
```

---

## 8. Evaluation Metrics Reference

### 8.1 Primary Fraud Detection Metrics

| Metric | Formula | Target | Baseline (rule engine v25) | Notes |
|---|---|---|---|---|
| AUROC | Area under ROC curve | > 0.93 | 0.71 | Primary ranking metric |
| Precision @ 5% FPR | Precision when FPR ≤ 0.05 | > 0.75 | 0.48 | Controls false alarm rate |
| Recall (fraud class) | TP / (TP + FN) | > 0.88 | 0.62 | Missed fraud = financial loss |
| F1 Score (fraud class) | 2 × P × R / (P + R) | > 0.80 | 0.54 | Threshold: 0.8 recommended |
| Latency P95 | 95th percentile end-to-end ms | < 800 ms | N/A | Full pipeline measured |

### 8.2 Bonus Evaluation Criteria

| Criterion | Bonus | Evidence Required |
|---|---|---|
| Zero false negatives on 10 seeded guaranteed-fraud transactions | +7% | Predict fraud on all 10 seeded `txn_id`s — list provided at evaluation day |
| OTP interlock correctly triggered for all SIM-swap cases | +5% | `otp_submission.csv` with `sim_swap` rows marked for escalation |
| Discovers COMM-042 smurfing community via graph analysis | +5% | `community_detection.json` listing all 7 member accounts |
| Dynamic synthesis weight adaptation by `txn_type` | +5% | Show different agent weights for ESEWA_P2P vs KHALTI_QR vs SWIFT_OUTWARD |
| SHAP or LIME explanations per decision | +3% | `shap_values.csv` with top-5 features per transaction in evaluation set |

### 8.3 Baseline Results (for reference)

| Model | AUROC | Recall | F1 (thr=0.5) | F1 (thr=0.8) | FPR |
|---|---|---|---|---|---|
| Logistic Regression | 0.550 | 19.3% | 0.053 | — | 11.4% |
| XGBoost | 0.984 | 89.1% | 0.672 | 0.856 | 1.40% |
| LightGBM | 0.983 | 88.9% | 0.668 | 0.829 | 1.42% |
| Ensemble (XGB+LGB) | **0.984** | **89.2%** | **0.674** | 0.829 | **1.39%** |
| Rule engine v25 | 0.710 | 62.0% | 0.540 | — | 14.0% |

> Top 5 features (LightGBM importance): `z_score_amount`, `prev_txn_time_delta_min`,
> `prev_txn_km`, `km_from_home_district`, `log(amount_npr)`

### 8.4 Submission Format

Submit a CSV named `submission_[team_name].csv`:

| Column | Type | Required | Description |
|---|---|---|---|
| `txn_id` | STRING | Yes | Transaction ID from evaluation set |
| `fraud_probability` | FLOAT | Yes | Model's fraud score 0.0–1.0. AUROC computed from this |
| `fraud_decision` | ENUM | Yes | `ALLOW` / `OTP_ONLY` / `BLOCK` |
| `fraud_type_predicted` | STRING | No | Optional — for bonus fraud-type classification scoring |
| `agent_scores_json` | STRING | No | JSON string of individual agent scores |
| `latency_ms` | INT | Yes | Inference time per transaction. P95 must be < 800 ms |

---

*This document is part of the GIBL AI/ML Hackathon 2026 — Track B dataset package.*

*Generated by the GIBL Hackathon Technical Committee, June 2026.*
