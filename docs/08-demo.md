# 08 — Demo Guide

An 8-minute walkthrough for the judging session. The numbers you quote should come from the
live dashboard and the committed [`benchmarks/eval_report.txt`](../benchmarks/eval_report.txt),
not from memory — quoting measured figures you can show on screen is far more convincing than
asserting round numbers.

## Pre-demo checklist (30 minutes before)

```bash
# 1. Start all services
bash scripts/start_all.sh

# 2. Verify health
curl http://localhost:8000/health
open http://localhost:3000          # dashboard

# 3. Pre-warm caches so the first live transactions aren't cold
python3 data/generators/replay.py & sleep 30; pkill -f replay.py

# 4. Open backup tabs
open http://localhost:8000/docs     # API docs
open http://localhost:5050          # MLflow

# 5. Click each of the 5 scenario buttons once to confirm they work
# 6. Have the fallback screen recording ready
```

## 8-minute flow

### 0–1 min — Introduction
> "SENTINEL is a multi-agent fraud-detection system for Track B. The brief named four
> challenges — minimize false positives, adapt to transaction context, protect new accounts,
> and defeat SIM-swap. I'll show how each is handled, end to end, in real time."

Show the dashboard at rest. Point out the four agents and the verdict band (ALLOW /
OTP_INTERLOCK / BLOCK).

### 1–3 min — Live traffic
```bash
python3 data/generators/replay.py
```
> "These are transactions flowing through the live pipeline."

Point out the colour coding (green ALLOW, amber OTP_INTERLOCK, red BLOCK). Click one
transaction and read its agent breakdown from the inspector — each transaction carries the four
agent scores and their reason codes, scored in parallel.

### 3–5 min — The Sita scenario (the centrepiece)
Click **Sita Attack**.
> "Sita is a teacher in Kathmandu. At 2am, someone attempts an NPR 85,000 payment from a new
> device ~800 km away."

Walk the inspector live:
- Read each agent's score and reason codes off the screen (velocity, geo, behavior, GNN).
- Show the per-type weights: this is a QR payment, so geo and velocity dominate and the graph
  agent contributes little.
- Read the composite score and the resulting verdict, and the latency the dashboard reports.

> "The point is the weighting: the same scores would fuse differently for a SWIFT transfer,
> where the graph agent leads."

### 5–6 min — SIM-swap defense
Click **SIM Swap**.
> "When a transaction needs verification we require OTPs on two independent channels. Here the
> attacker has cloned the SIM and receives the SMS code — but cannot reach the victim's email.
> SMS passes, Email fails, so we BLOCK with a sim-swap alert. That asymmetry is the signal."

### 6–7 min — Cold-start protection
Click **Cold Start**.
> "A five-day-old overseas-worker account has no personal history. We assign it to a peer
> cohort and use that cohort's model from day 0. A normal inbound remittance is allowed; an
> unusual outbound transfer is escalated to verification."

### 7–8 min — Results and wrap-up
Show the stats panel, and have `benchmarks/eval_report.txt` open.
> "Latency and detection are measured — here is the benchmark report and the test suite. The
> verdict budget is 800ms P99; our measured end-to-end latency is well inside it. All four
> challenges are handled by explicit mechanisms, not a single opaque model."

If time allows, show MLflow (six cohorts, two models each).

## Scenario reference

Each scenario is registered in `tests/scenarios/` and exposed at
`POST /scenarios/run/{name}`. Quote the verdict and the agent breakdown the system returns
live, rather than pre-stating a score.

| Scenario | Setup | Expected verdict | Why |
|----------|-------|------------------|-----|
| Sita — attack | 2am, NPR 85K, new device, ~800 km from home, QR | BLOCK | Impossible travel + new device + off-hours + large amount |
| Sita — legit | 11am, NPR 1.2K, known device, home district | ALLOW | All signals normal |
| SIM-swap | Suspicious txn → OTP; SMS ✓, Email ✗ | BLOCK (`sim_swap_alert`) | Independent channels; email can't be reached via SIM |
| Cold-start | Day-5 overseas-worker account | inbound ALLOW / outbound escalated | Cohort model from day 0 |
| Mule ring | 5 sources → 1 mule → 1 destination within 2h | escalated | Graph agent flags the fan-in/forward pattern |

## Talking points

- **Context-aware synthesis** — "Different transaction types fail in different ways. A QR
  payment is location-driven; a SWIFT transfer is graph-driven. The synthesis weights encode
  that, instead of treating every signal as equally relevant."
- **Multi-agent, not monolithic** — "Four specialized agents run in parallel, so latency is
  bounded by the slowest, not the sum. If one times out, the others still produce a verdict —
  the missing score is imputed neutral."
- **Reproducible** — "Every number we quote comes from `pytest` and `benchmark_synthetic.py`;
  the report is in the repo."

## Q&A preparation

**How do you handle the real data format?**
> "An adapter pattern. `data/adapters/real_data_adapter.py` is the only place that knows the raw
> payload shape; everything downstream consumes our internal `TransactionEvent`. When the real
> files arrive we fill in the field maps there — no agent changes."

**What about adversarial attacks on the models?**
> "Ensemble voting across four independent agents raises the bar — an attacker has to fool all
> of them at once — and MLflow drift monitoring flags accuracy regressions for retraining."

**How do you avoid bias across customer types?**
> "Per-cohort models, so an overseas worker isn't penalised for differing from a salaried urban
> account. Every decision is audited in Postgres for investigation."

**Why these synthesis weights?**
> "Domain reasoning about where each transaction type's fraud actually shows up — QR fraud is
> location-based, SWIFT fraud is network-based. They're explicit and tunable, and the eval
> harness lets us measure any change."

**Can it scale?**
> "The orchestrator is stateless behind Kafka; throughput scales by adding consumers. Measured
> single-process throughput is in the benchmark report; horizontal scaling is in
> [07-performance.md](./07-performance.md)."

## Backup plans

- **Live demo fails** → narrate over the pre-recorded screen capture of all five scenarios.
- **Need to show without the UI** → `curl -X POST http://localhost:8000/scenarios/run/sita | jq`
  and walk the JSON.
- **Services won't start** → `docker compose down -v && docker compose up -d && bash scripts/init_kafka.sh && bash scripts/seed_all.sh`.

## Final checklist

- [ ] All services healthy; caches pre-warmed
- [ ] All five scenario buttons tested
- [ ] `benchmarks/eval_report.txt` and a terminal with `pytest` output open as evidence
- [ ] Browser full-screen, zoomed for projector, notifications muted
- [ ] Fallback recording ready
