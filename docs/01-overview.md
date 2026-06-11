# 01 — Project Overview

## Problem statement

### The challenge
Financial institutions in Nepal operate in a demanding fraud environment. With large annual
remittance flows and tens of millions of mobile-banking users, banks like Global IME are
exposed to fraud vectors that generic, globally-trained models detect poorly — they miss
locally-specific patterns and over-flag ordinary Nepali behaviour.

### Nepal-specific fraud landscape
SENTINEL targets six primary threat vectors in the Nepalese context:

1. **Remittance interception** — fraudulent beneficiary substitution during SWIFT transfers.
2. **SIM-swap account takeover** — duplicate SIM used to intercept OTPs (NTC/Ncell).
3. **eSewa / QR fraud** — stolen QR codes or compromised merchant accounts.
4. **Velocity / structuring** — sub-threshold bursts spread across mule accounts.
5. **New-device takeover** — account access from a previously unseen device fingerprint.
6. **Synthetic identity / KYC fraud** — fake documents used to open mule accounts.

### Track B requirements
Track B asks for a multi-agent ML system that scores each transaction through several
specialized models, synthesizes their verdicts through a context-aware orchestrator, and
triggers dual-path OTP verification when fraud is suspected. The problem statement names four
key challenges:

1. **Minimize false positives** — a blocked legitimate customer is churn.
2. **Context-aware detection** — weights should adapt to transaction context (remittance vs POS vs QR).
3. **Cold-start protection** — new users have no behavioural history.
4. **SIM-swap defense** — the highest-impact attack vector in Nepal.

These four challenges structure the rest of this document.

## Related work

SENTINEL's design draws on established literature:

- **Recall/precision trade-off** — Bolton & Hand (2002) frame the core tension that the
  graduated verdict band (allow / verify / block) is designed to manage.
- **Anomaly detection** — Liu et al. (2008) introduced the Isolation Forest, used here to flag
  novel patterns outside the labelled training distribution.
- **Sequence modelling** — Hochreiter & Schmidhuber (1997) introduced the LSTM, used to model a
  customer's behaviour over time.
- **Graph analytics** — Zhou et al. (2021) showed GNNs detect laundering rings, informing the
  Neo4j-based graph agent.
- **MFA security** — Bonneau et al. (2012) and Conti et al. (2018) document the weakness of
  SMS-only OTP and motivate the independent dual-path design.

## The solution: a multi-agent system

Rather than one monolithic model, SENTINEL scores every transaction through four specialized
agents in parallel, then fuses their scores with weights chosen by transaction type.

**Why multi-agent:**
- **Specialization** — each agent targets a distinct fraud signal.
- **Parallelism** — agents run concurrently, so latency is bounded by the slowest, not the sum.
- **Robustness** — if one agent times out, the others still produce a verdict (the missing score
  is imputed to a neutral 0.5).
- **Explainability** — the verdict carries each agent's score and reason codes.

### The four agents

| Agent | Type | Detects |
|-------|------|---------|
| **Velocity** | Redis sliding-window counters | Burst attacks, structuring, dormancy breaks |
| **Geo** | Heuristic geo-velocity + device fingerprint | Impossible travel, new devices, VPN/Tor, SIM change |
| **Behavior** | Per-cohort LSTM + Isolation Forest ensemble | Anomalous amount, timing, and counterparty patterns |
| **GNN** | Neo4j Cypher graph queries | Money-mule rings and layering |

Per-agent algorithms are in [05-agents.md](./05-agents.md); measured latencies are in
[07-performance.md](./07-performance.md).

### The key innovation: context-aware synthesis

Not every signal matters equally for every transaction type. A QR payment has no counterparty
graph to speak of, but its location is highly informative; a SWIFT remittance is the opposite.
The Synthesis Agent encodes this as a per-type weight vector:

```python
WEIGHTS_BY_TYPE = {
    "KHALTI_QR":     {"velocity": 0.35, "geo": 0.35, "behavior": 0.25, "gnn": 0.05},
    "ATM_WITHDRAWAL":{"velocity": 0.30, "geo": 0.45, "behavior": 0.20, "gnn": 0.05},
    "ESEWA_P2P":     {"velocity": 0.20, "geo": 0.15, "behavior": 0.25, "gnn": 0.40},
    "SWIFT_OUTWARD": {"velocity": 0.15, "geo": 0.20, "behavior": 0.20, "gnn": 0.45},
    # ... one entry per Track-B transaction type
}
```

A QR payment leans on geo and velocity (no counterparty graph), while a SWIFT transfer leans on
the graph agent for mule detection. An unknown type falls back to a balanced vector, and the
composite is clamped to `[0, 1]`. This directly answers Track B's context-aware requirement and
is the bonus-eligible weight-adaptation feature (§8.2). The full table is in
[`agents/synthesis/agent.py`](../agents/synthesis/agent.py).

## How each challenge is addressed

### 1. Minimize false positives — a graduated verdict band
Instead of a binary allow/block, the composite score routes to one of three outcomes:

- `< 0.40` → **ALLOW**
- `0.40 – 0.75` → **OTP_INTERLOCK** (verify, don't block)
- `> 0.75` → **BLOCK**

A suspicious-but-not-certain transaction is verified, not refused, so a legitimate customer can
still complete it after passing OTP.

### 2. Context-aware detection — per-type weights
The weight vectors above mean each transaction type is judged by the signals that actually
predict its fraud, rather than a one-size-fits-all model.

### 3. Cold-start protection — cohort models from day 0
A new account is assigned to one of six peer cohorts (by account type and home district) and
inherits that cohort's trained models immediately. A four-stage onboarding tightens controls
while personal history accrues:

| Stage | Age | Controls |
|-------|-----|----------|
| 1 | days 0–3 | Strict NRB rule limits |
| 2 | days 4–14 | Cohort models |
| 3 | days 15–30 | Hybrid (cohort blended with personal) |
| 4 | day 31+ | Personal models |

### 4. SIM-swap defense — independent dual-path OTP
Verification requires confirming codes on **both** SMS and Email within a five-minute window.
The state machine treats channel-specific failures as signal:

- both confirm → **RELEASE**
- SMS fails, Email confirms → **BLOCK** (SIM-swap signature)
- SMS confirms, Email fails → **HUMAN_REVIEW**
- both fail → **BLOCK**

An attacker who has cloned the SIM still cannot reach the victim's email, so the asymmetric
failure exposes the attack.

## Results

Latency and detection metrics are measured, not asserted — see
[07-performance.md](./07-performance.md) and the committed
[`benchmarks/eval_report.txt`](../benchmarks/eval_report.txt) for the current run and the exact
method used to produce it. Eval-day metrics against the official Track-B data come from
`scripts/evaluate.py`, which reports against the §8.1 targets and the §8.3 baseline.

## Demo scenarios

The dashboard ships five end-to-end scenarios (see [08-demo.md](./08-demo.md)):

1. **Sita — attack** — 2am, NPR 85K, new device, ~800 km from home → all agents flag → BLOCK.
2. **Sita — legitimate** — 11am, NPR 1.2K, known device, home district → ALLOW.
3. **SIM-swap** — SMS confirms, Email fails → BLOCK (SIM-swap detected).
4. **Cold-start** — day-5 overseas-worker account → legit inbound ALLOWed via cohort model;
   suspicious outbound escalated.
5. **Mule ring** — five sources → one mule → one destination → graph agent flags the ring.

---

Next: [02 — Architecture](./02-architecture.md)
