# SENTINEL — Technical Documentation

Multi-agent, real-time fraud detection for Nepal's banking sector.
Global IME AI/ML Hackathon 2026 · Track B — Security & Fraud.

For the project summary and quick start, see the [root README](../README.md).
This folder is the in-depth technical reference.

## Reading order

| # | Document | What it covers |
|---|----------|----------------|
| 01 | [Overview](./01-overview.md) | Problem, the Nepal fraud landscape, related work, and the multi-agent solution |
| 02 | [Architecture](./02-architecture.md) | Request flow, parallel agent execution, timeout handling, scalability |
| 03 | [Tech stack](./03-tech-stack.md) | Each technology choice and the alternatives considered |
| 04 | [Setup](./04-setup.md) | Installation, configuration, and deployment (see also [/SETUP.md](../SETUP.md)) |
| 05 | [Agents](./05-agents.md) | Per-agent algorithms, signals, and reason codes |
| 06 | [Data flow](./06-data-flow.md) | A transaction's journey from ingestion to audited verdict |
| 07 | [Performance](./07-performance.md) | Measured latency and detection results, and how they were obtained |
| 08 | [Demo](./08-demo.md) | Presentation script and scenario walkthroughs |
| 09 | [Track-B submission](./09-track-b-submission.md) | Eval-day pipeline: scoring the official data and producing the submission |

## Reference

- [decisions.md](./decisions.md) — architecture decision records (why each major choice was made)
- [schemas.md](./schemas.md) — data contracts (`TransactionEvent`, `AgentScore`, `SynthesisVerdict`)

## Where the numbers come from

Every performance figure in these docs is reproducible, not asserted:

- **Detection quality and latency** — `python3 scripts/benchmark_synthetic.py` replays the
  labelled synthetic seeds through the live agents and writes [`benchmarks/eval_report.txt`](../benchmarks/eval_report.txt).
- **Eval-day metrics** — `python3 scripts/evaluate.py --data structured` scores the official
  Track-B data against the §8.1 targets and the §8.3 rule-engine baseline.
- **Tests** — `python3 -m pytest -q`.

See [07-performance.md](./07-performance.md) for the current results and methodology.
