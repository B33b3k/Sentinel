// Deterministic-ish simulated transaction generator for the standalone (backend-less) demo.
// Mirrors the shapes produced by the real orchestrator (see orchestrator/schemas.py) and the
// real context-aware weights (see agents/synthesis/agent.py) so the demo is representative of
// actual SENTINEL behavior — it is simulated traffic, not simulated logic.

export type Verdict = "ALLOW" | "OTP_INTERLOCK" | "BLOCK";

export interface AgentScore {
  agent: string;
  score: number;
  reason_codes: string[];
  latency_ms: number;
}

export interface Transaction {
  transaction_id: string;
  account_id: string;
  composite_score: number;
  verdict: Verdict;
  agent_scores: AgentScore[];
  weights_used: Record<string, number>;
  transaction_type: string;
  total_latency_ms: number;
}

export interface Stats {
  total: number;
  allow: number;
  otp_interlock: number;
  block: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  fraud_by_type: Record<string, number>;
}

export interface OTPPending {
  tx_id: string;
  account_id: string;
  phone: string;
  email: string;
  triggered_at: number;
}

// Real per-type weight vectors, copied from agents/synthesis/agent.py WEIGHTS_BY_TYPE.
const WEIGHTS_BY_TYPE: Record<string, Record<string, number>> = {
  ESEWA_P2P: { velocity: 0.2, geo: 0.15, behavior: 0.25, gnn: 0.4 },
  KHALTI_QR: { velocity: 0.35, geo: 0.35, behavior: 0.25, gnn: 0.05 },
  CARD_POS: { velocity: 0.25, geo: 0.4, behavior: 0.3, gnn: 0.05 },
  ATM_WITHDRAWAL: { velocity: 0.3, geo: 0.45, behavior: 0.2, gnn: 0.05 },
  SWIFT_OUTWARD: { velocity: 0.15, geo: 0.2, behavior: 0.2, gnn: 0.45 },
  RTGS: { velocity: 0.15, geo: 0.15, behavior: 0.25, gnn: 0.45 },
  MOBILE_TOPUP: { velocity: 0.4, geo: 0.25, behavior: 0.3, gnn: 0.05 },
  UTILITY_BILL: { velocity: 0.3, geo: 0.25, behavior: 0.4, gnn: 0.05 },
};
const TX_TYPES = Object.keys(WEIGHTS_BY_TYPE);

const REASON_CODES: Record<string, string[]> = {
  velocity: ["burst_txn_count", "rapid_succession", "dormancy_break", "structuring_pattern"],
  geo: ["impossible_travel", "new_device", "vpn_detected", "sim_change", "known_location"],
  behavior: ["amount_anomaly", "timing_anomaly", "new_counterparty", "cohort_deviation"],
  gnn: ["mule_ring_proximity", "layering_pattern", "recent_beneficiary", "clean_graph"],
};

let seq = 0;
const rand = (min: number, max: number) => min + Math.random() * (max - min);
const pick = <T,>(arr: T[]) => arr[Math.floor(Math.random() * arr.length)];

function scoreFor(agent: string, fraudulent: boolean): number {
  const base = fraudulent ? rand(0.45, 0.97) : rand(0.02, 0.35);
  return Math.min(1, Math.max(0, base + rand(-0.08, 0.08)));
}

export function generateTransaction(forceFraud?: boolean): Transaction {
  seq += 1;
  const txType = pick(TX_TYPES);
  const weights = WEIGHTS_BY_TYPE[txType];
  const fraudulent = forceFraud ?? Math.random() < 0.08;

  const agent_scores: AgentScore[] = (["velocity", "geo", "behavior", "gnn"] as const).map((agent) => {
    const score = scoreFor(agent, fraudulent);
    const latency = agent === "behavior" ? rand(4, 19) : agent === "velocity" ? rand(1, 9) : rand(0.2, 4);
    return {
      agent,
      score,
      reason_codes: [pick(REASON_CODES[agent])],
      latency_ms: latency,
    };
  });

  const composite = agent_scores.reduce((sum, s) => sum + s.score * (weights[s.agent] ?? 0.25), 0);
  const clamped = Math.min(1, Math.max(0, composite));
  const verdict: Verdict = clamped < 0.4 ? "ALLOW" : clamped < 0.75 ? "OTP_INTERLOCK" : "BLOCK";
  const total_latency_ms = Math.max(...agent_scores.map((s) => s.latency_ms)) + rand(0.5, 2.5);

  return {
    transaction_id: `sim-${Date.now().toString(36)}-${seq}`,
    account_id: `NP-${Math.floor(rand(100000, 999999))}`,
    composite_score: clamped,
    verdict,
    agent_scores,
    weights_used: weights,
    transaction_type: txType,
    total_latency_ms,
  };
}

export const SCENARIO_PRESETS: Record<string, { forceFraud: boolean; txType?: string }> = {
  sita: { forceFraud: true, txType: "MOBILE_TOPUP" },
  sita_legit: { forceFraud: false, txType: "ESEWA_P2P" },
  sim_swap: { forceFraud: true, txType: "ATM_WITHDRAWAL" },
  cold_start: { forceFraud: false, txType: "ESEWA_P2P" },
  mule_ring: { forceFraud: true, txType: "SWIFT_OUTWARD" },
};

export function generateScenario(id: string): Transaction {
  const preset = SCENARIO_PRESETS[id];
  const tx = generateTransaction(preset?.forceFraud);
  if (preset?.txType) {
    tx.transaction_type = preset.txType;
    tx.weights_used = WEIGHTS_BY_TYPE[preset.txType];
  }
  return tx;
}

export function computeStats(txs: Transaction[]): Stats {
  const latencies = txs.map((t) => t.total_latency_ms).sort((a, b) => a - b);
  const pct = (p: number) => (latencies.length ? latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * p))] : 0);
  const fraud_by_type: Record<string, number> = {};
  for (const t of txs) {
    if (t.verdict !== "ALLOW") fraud_by_type[t.transaction_type] = (fraud_by_type[t.transaction_type] || 0) + 1;
  }
  return {
    total: txs.length,
    allow: txs.filter((t) => t.verdict === "ALLOW").length,
    otp_interlock: txs.filter((t) => t.verdict === "OTP_INTERLOCK").length,
    block: txs.filter((t) => t.verdict === "BLOCK").length,
    p50_ms: pct(0.5),
    p95_ms: pct(0.95),
    p99_ms: pct(0.99),
    fraud_by_type,
  };
}

export function generatePendingOTP(txs: Transaction[]): OTPPending[] {
  return txs
    .filter((t) => t.verdict === "OTP_INTERLOCK")
    .slice(0, 3)
    .map((t) => ({
      tx_id: t.transaction_id,
      account_id: t.account_id,
      phone: "+977-98********",
      email: "u***@example.com",
      triggered_at: Date.now() / 1000,
    }));
}
