# Scope Decisions

These decisions lock Sprint 0 scope so implementation can move quickly without re-litigating the demo architecture.

## D1: Real ML vs heuristic per agent

Velocity and Geo agents are heuristic. Behavior and GNN are real ML, with a Cypher fallback for graph detection if GraphSAGE is not ready in time.

## D2: SMS provider strategy

OTP delivery is mocked by default. A single real Twilio demo path may be enabled if trial credit and phone verification allow it.

## D3: Kafka vs direct calls

Kafka is the primary event bus. `KAFKA_ENABLED=false` remains available as a local fallback for demos and tests.

## D4: Data source

Synthetic data is the canonical source. The target dataset is about 5,000 accounts with 20-50 transactions each and about 2% labeled fraud.

## D5: Hosting

The primary demo runs from a laptop. A single VM can be used as backup failover.

## D6: Per-account vs per-cohort behavior ML

Behavior modeling is per cohort only, with 5-10 cohorts total.

## D7: GNN scope

GraphSAGE is the target. If training is not ready in time, the mule-ring Cypher query ships as graph-based detection.
