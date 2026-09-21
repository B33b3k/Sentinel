// Single point where the dashboard chooses between the real SENTINEL backend (Kafka → orchestrator
// → WebSocket, used for local/full-stack runs) and the simulated in-browser backend used for the
// standalone public demo (no server required — see README "Demo mode" for why).
import {
  Transaction,
  Stats,
  OTPPending,
  generateTransaction,
  generateScenario,
  computeStats,
  generatePendingOTP,
} from "./mock";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/verdicts";

// ─── Demo (simulated) backend ──────────────────────────────────────────────
const demoHistory: Transaction[] = [];
const demoPendingUntil = new Map<string, number>();
const MAX_HISTORY = 200;

function pushDemoTx(tx: Transaction) {
  demoHistory.unshift(tx);
  if (demoHistory.length > MAX_HISTORY) demoHistory.length = MAX_HISTORY;
  if (tx.verdict === "OTP_INTERLOCK") {
    demoPendingUntil.set(tx.transaction_id, Date.now() + 6000);
  }
}

export async function getStats(): Promise<Stats> {
  if (DEMO_MODE) return computeStats(demoHistory);
  const res = await fetch(`${API}/stats`);
  return res.json();
}

export async function runScenario(id: string): Promise<Transaction> {
  if (DEMO_MODE) {
    const tx = generateScenario(id);
    pushDemoTx(tx);
    return tx;
  }
  const res = await fetch(`${API}/scenarios/run/${id}`, { method: "POST" });
  return res.json();
}

export async function getPendingOTP(): Promise<OTPPending[]> {
  if (DEMO_MODE) {
    const now = Date.now();
    for (const [id, until] of demoPendingUntil) {
      if (until < now) demoPendingUntil.delete(id);
    }
    const live = demoHistory.filter((t) => demoPendingUntil.has(t.transaction_id));
    return generatePendingOTP(live);
  }
  const res = await fetch(`${API}/otp/pending`);
  return res.json();
}

export type StreamStatus = "connecting" | "open" | "closed";

export function subscribeStream(
  onMessage: (tx: Transaction) => void,
  onStatus: (status: StreamStatus) => void,
): () => void {
  if (DEMO_MODE) {
    onStatus("connecting");
    const startDelay = setTimeout(() => onStatus("open"), 400);
    const interval = setInterval(() => {
      const tx = generateTransaction();
      pushDemoTx(tx);
      onMessage(tx);
    }, 1400);
    return () => {
      clearTimeout(startDelay);
      clearInterval(interval);
    };
  }

  let ws: WebSocket | null = null;
  let closedByCaller = false;

  const connect = () => {
    ws = new WebSocket(WS_URL);
    onStatus("connecting");
    ws.onopen = () => onStatus("open");
    ws.onclose = () => {
      onStatus("closed");
      if (!closedByCaller) setTimeout(connect, 2000);
    };
    ws.onerror = () => onStatus("closed");
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch {
        /* ignore malformed frame */
      }
    };
  };
  connect();

  return () => {
    closedByCaller = true;
    ws?.close();
  };
}
