import { useState, useEffect, useRef, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line,
} from "recharts";
import {
  AlertTriangle, CheckCircle, XCircle, Zap, RefreshCw,
  ShieldAlert, Users, Globe, Activity,
} from "lucide-react";

const API = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/verdicts";

type Verdict = "ALLOW" | "OTP_INTERLOCK" | "BLOCK";

interface AgentScore {
  agent: string;
  score: number;
  reason_codes: string[];
  latency_ms: number;
}
interface Transaction {
  transaction_id: string;
  account_id: string;
  composite_score: number;
  verdict: Verdict;
  agent_scores: AgentScore[];
  weights_used: Record<string, number>;
  transaction_type: string;
  total_latency_ms: number;
}
interface Stats {
  total: number;
  allow: number;
  otp_interlock: number;
  block: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  fraud_by_type: Record<string, number>;
}
interface OTPPending {
  tx_id: string;
  account_id: string;
  phone: string;
  email: string;
  triggered_at: number;
}

const VERDICT_COLOR: Record<Verdict, string> = {
  ALLOW: "text-emerald-400",
  OTP_INTERLOCK: "text-amber-400",
  BLOCK: "text-red-400",
};
const VERDICT_BG: Record<Verdict, string> = {
  ALLOW: "bg-emerald-950/50 border-emerald-800",
  OTP_INTERLOCK: "bg-amber-950/50 border-amber-800",
  BLOCK: "bg-red-950/50 border-red-800",
};
const CHART_COLORS = ["#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#8b5cf6"];

const SCENARIOS: { id: string; label: string; desc: string; icon: React.ReactNode; color: string }[] = [
  { id: "sita",       label: "Sita Attack",    desc: "2am · NPR 85K · new device · Dharan",         icon: <ShieldAlert size={15} />, color: "bg-red-700 hover:bg-red-600" },
  { id: "sita_legit", label: "Sita Legit",     desc: "11am · NPR 1.2K · known device · Kathmandu",  icon: <CheckCircle size={15} />, color: "bg-emerald-700 hover:bg-emerald-600" },
  { id: "sim_swap",   label: "SIM Swap",       desc: "Correct SMS, wrong email → BLOCK",             icon: <AlertTriangle size={15} />, color: "bg-orange-700 hover:bg-orange-600" },
  { id: "cold_start", label: "Cold Start",     desc: "Day-5 overseas worker account",                icon: <Users size={15} />, color: "bg-blue-700 hover:bg-blue-600" },
  { id: "mule_ring",  label: "Mule Ring",      desc: "5 sources → mule → destination",              icon: <Globe size={15} />, color: "bg-purple-700 hover:bg-purple-600" },
];

// ─── TransactionStream ────────────────────────────────────────────────────────
function TransactionStream({ txs, onSelect, selected }: {
  txs: Transaction[];
  onSelect: (t: Transaction) => void;
  selected: Transaction | null;
}) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-2">
        Live Stream
      </h2>
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        {txs.length === 0 && (
          <p className="text-gray-600 text-xs mt-4 text-center">Waiting for transactions…</p>
        )}
        {txs.map((tx) => (
          <button
            key={tx.transaction_id}
            onClick={() => onSelect(tx)}
            className={`w-full text-left rounded-lg border px-3 py-2 text-xs transition-all ${VERDICT_BG[tx.verdict]} ${
              selected?.transaction_id === tx.transaction_id
                ? "ring-1 ring-white/40"
                : "opacity-80 hover:opacity-100"
            }`}
          >
            <div className="flex justify-between items-center">
              <span className="font-mono text-gray-300 truncate max-w-[100px]">{tx.account_id}</span>
              <span className={`font-bold text-xs ${VERDICT_COLOR[tx.verdict]}`}>{tx.verdict}</span>
            </div>
            <div className="flex justify-between text-gray-500 mt-0.5">
              <span>{tx.transaction_type}</span>
              <span>{tx.composite_score.toFixed(3)}</span>
              <span>{tx.total_latency_ms.toFixed(0)}ms</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── TransactionInspector ─────────────────────────────────────────────────────
function TransactionInspector({ tx }: { tx: Transaction | null }) {
  if (!tx) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-600 gap-2">
        <Activity size={32} />
        <span className="text-sm">Select a transaction to inspect</span>
      </div>
    );
  }

  const agentData = tx.agent_scores.map((s) => ({
    name: s.agent,
    score: parseFloat(s.score.toFixed(3)),
    weight: tx.weights_used[s.agent] ?? 0,
    latency: s.latency_ms,
  }));

  const scorePos = `${Math.min(tx.composite_score * 100, 99)}%`;

  return (
    <div className="flex flex-col h-full min-h-0 gap-4 overflow-y-auto pr-1">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest shrink-0">
        Inspector
      </h2>

      {/* Summary row */}
      <div className="flex flex-wrap gap-3 text-sm shrink-0">
        <span className={`font-black text-lg ${VERDICT_COLOR[tx.verdict]}`}>{tx.verdict}</span>
        <span className="text-gray-300">
          composite <span className="font-bold text-white">{tx.composite_score.toFixed(4)}</span>
        </span>
        <span className="text-gray-500">{tx.transaction_type}</span>
        <span className="text-gray-500">{tx.total_latency_ms.toFixed(1)} ms</span>
        <span className="font-mono text-gray-600 text-xs self-center">
          {tx.transaction_id.slice(0, 8)}…
        </span>
      </div>

      {/* Threshold band */}
      <div className="relative h-7 rounded-lg overflow-hidden shrink-0">
        <div className="absolute inset-y-0 left-0 bg-emerald-900/70" style={{ width: "40%" }} />
        <div className="absolute inset-y-0 bg-amber-900/70" style={{ left: "40%", width: "35%" }} />
        <div className="absolute inset-y-0 right-0 bg-red-900/70" style={{ width: "25%" }} />
        {/* Score needle */}
        <div
          className="absolute inset-y-0 w-0.5 bg-white shadow-[0_0_6px_white]"
          style={{ left: scorePos }}
        />
        <div className="absolute inset-0 flex justify-between items-center px-3 text-xs text-white/50 pointer-events-none select-none">
          <span>ALLOW &lt;0.40</span>
          <span>OTP 0.40–0.75</span>
          <span>BLOCK &gt;0.75</span>
        </div>
      </div>

      {/* Agent scores */}
      <div className="shrink-0">
        <ResponsiveContainer width="100%" height={110}>
          <BarChart data={agentData} margin={{ top: 0, right: 4, left: -24, bottom: 0 }}>
            <XAxis dataKey="name" tick={{ fill: "#6b7280", fontSize: 11 }} />
            <YAxis domain={[0, 1]} tick={{ fill: "#6b7280", fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 11 }}
              formatter={(v: number, name: string) => [v.toFixed(3), name]}
            />
            <Bar dataKey="score" radius={[3, 3, 0, 0]}>
              {agentData.map((a, i) => (
                <Cell
                  key={i}
                  fill={a.score >= 0.75 ? "#ef4444" : a.score >= 0.40 ? "#f59e0b" : "#10b981"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Weights */}
      <div className="grid grid-cols-4 gap-2 text-xs text-center shrink-0">
        {agentData.map((a) => (
          <div key={a.name} className="bg-gray-800/60 rounded-lg p-2 border border-gray-700/50">
            <div className="text-gray-500 capitalize">{a.name}</div>
            <div className="text-white font-bold">{(a.weight * 100).toFixed(0)}%</div>
            <div className="text-gray-600">{a.latency.toFixed(1)}ms</div>
          </div>
        ))}
      </div>

      {/* Reason codes */}
      <div className="space-y-1.5 shrink-0">
        {tx.agent_scores
          .filter((s) => s.reason_codes.length > 0)
          .map((s) => (
            <div key={s.agent} className="flex flex-wrap gap-1 items-center">
              <span className="text-gray-500 text-xs capitalize w-16 shrink-0">{s.agent}</span>
              {s.reason_codes.map((r) => (
                <span
                  key={r}
                  className="bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-xs text-gray-300 font-mono"
                >
                  {r}
                </span>
              ))}
            </div>
          ))}
      </div>
    </div>
  );
}

// ─── ScenarioPanel ────────────────────────────────────────────────────────────
function ScenarioPanel({ onResult }: { onResult: (t: Transaction | object, scenarioId: string) => void }) {
  const [loading, setLoading] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { verdict?: string; composite_score?: number; reason?: string } | null>>({});

  const fire = async (id: string) => {
    setLoading(id);
    try {
      const res = await fetch(`${API}/scenarios/run/${id}`, { method: "POST" });
      const data = await res.json();
      setResults((prev) => ({ ...prev, [id]: data }));
      onResult(data, id);
    } catch {
      setResults((prev) => ({ ...prev, [id]: null }));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Scenarios</h2>
      {SCENARIOS.map((s) => {
        const res = results[s.id];
        // For cold_start, result is {legit: {...}, suspicious: {...}}
        const topVerdict: string | undefined =
          res && "verdict" in res ? (res as { verdict: string }).verdict
          : res && "legit" in res ? `legit:${(res as { legit: { verdict: string } }).legit.verdict}`
          : res && "reason" in res ? (res as { reason: string }).reason
          : undefined;

        return (
          <div key={s.id} className="flex items-center gap-2">
            <button
              onClick={() => fire(s.id)}
              disabled={loading !== null}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all disabled:opacity-40 shrink-0 ${s.color}`}
            >
              {loading === s.id ? <RefreshCw size={12} className="animate-spin" /> : s.icon}
              {s.label}
            </button>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-gray-500 truncate">{s.desc}</div>
              {topVerdict && (
                <div className={`text-xs font-bold truncate ${
                  topVerdict.includes("BLOCK") ? "text-red-400"
                  : topVerdict.includes("OTP") ? "text-amber-400"
                  : topVerdict.includes("ALLOW") || topVerdict.includes("legit") ? "text-emerald-400"
                  : topVerdict.includes("sim_swap") ? "text-red-400"
                  : "text-gray-400"
                }`}>
                  → {topVerdict}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── OTPViewer ────────────────────────────────────────────────────────────────
function OTPViewer() {
  const [pending, setPending] = useState<OTPPending[]>([]);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API}/otp/pending`);
        setPending(await res.json());
      } catch { /* infra not up */ }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest flex items-center gap-2">
        OTP Interlock
        {pending.length > 0 && (
          <span className="bg-amber-500 text-black text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
            {pending.length}
          </span>
        )}
      </h2>
      {pending.length === 0 ? (
        <p className="text-gray-600 text-xs">No pending verifications</p>
      ) : (
        pending.map((p) => (
          <div
            key={p.tx_id}
            className="bg-amber-950/40 border border-amber-800/60 rounded-lg p-2.5 text-xs space-y-1"
          >
            <div className="flex items-center gap-1.5">
              <AlertTriangle size={12} className="text-amber-400 shrink-0" />
              <span className="font-mono text-gray-300 truncate">{p.account_id}</span>
            </div>
            <div className="text-gray-500">📱 {p.phone}</div>
            <div className="text-gray-500">✉️ {p.email}</div>
            <div className="font-mono text-gray-600">tx: {p.tx_id.slice(0, 12)}…</div>
          </div>
        ))
      )}
    </div>
  );
}

// ─── StatsPanel ───────────────────────────────────────────────────────────────
function StatsPanel({ txs }: { txs: Transaction[] }) {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API}/stats`);
        setStats(await res.json());
      } catch { /* infra not up */ }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  const verdictDist = [
    { name: "ALLOW", value: stats?.allow ?? 0 },
    { name: "OTP", value: stats?.otp_interlock ?? 0 },
    { name: "BLOCK", value: stats?.block ?? 0 },
  ];

  const fraudByType = Object.entries(stats?.fraud_by_type ?? {}).map(([name, value]) => ({
    name, value,
  }));

  const latencyHistory = txs
    .slice(0, 60)
    .reverse()
    .map((t, i) => ({ i, ms: t.total_latency_ms }));

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Stats</h2>

      {/* Latency badges — real P99 from /stats */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {(["p50_ms", "p95_ms", "p99_ms"] as const).map((k) => (
          <div key={k} className="bg-gray-800/60 border border-gray-700/50 rounded-lg py-1.5">
            <div className="text-gray-500 text-xs">{k.replace("_ms", "").toUpperCase()}</div>
            <div className="text-white font-bold text-sm">
              {stats ? `${stats[k].toFixed(0)}ms` : "—"}
            </div>
          </div>
        ))}
      </div>

      {/* Latency sparkline */}
      {latencyHistory.length > 1 && (
        <ResponsiveContainer width="100%" height={50}>
          <LineChart data={latencyHistory}>
            <Line type="monotone" dataKey="ms" stroke="#3b82f6" dot={false} strokeWidth={1.5} />
            <YAxis hide domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 10 }}
              formatter={(v: number) => [`${v.toFixed(1)}ms`, "latency"]}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {/* Verdict distribution */}
      <div className="flex items-center gap-2">
        <ResponsiveContainer width={80} height={80}>
          <PieChart>
            <Pie data={verdictDist} dataKey="value" cx="50%" cy="50%" outerRadius={35} innerRadius={18}>
              {verdictDist.map((_, i) => (
                <Cell key={i} fill={CHART_COLORS[i]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="flex-1 space-y-1 text-xs">
          {verdictDist.map((d, i) => (
            <div key={d.name} className="flex justify-between">
              <span style={{ color: CHART_COLORS[i] }}>{d.name}</span>
              <span className="text-gray-400">{d.value}</span>
            </div>
          ))}
          {stats && (
            <div className="text-gray-600 pt-1 border-t border-gray-800">
              total: <span className="text-gray-400">{stats.total}</span>
            </div>
          )}
        </div>
      </div>

      {/* Fraud by type */}
      {fraudByType.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 mb-1">Flagged by type</div>
          <ResponsiveContainer width="100%" height={60}>
            <BarChart data={fraudByType} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fill: "#6b7280", fontSize: 9 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 9 }} />
              <Bar dataKey="value" fill="#f59e0b" radius={[2, 2, 0, 0]} />
              <Tooltip
                contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 10 }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [stats, setStats] = useState<Stats | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Poll /stats for the header P99 badge
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API}/stats`);
        setStats(await res.json());
      } catch { /* ok */ }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onopen = () => setWsStatus("open");
    ws.onclose = () => {
      setWsStatus("closed");
      setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const tx: Transaction = JSON.parse(e.data);
        setTxs((prev) => [tx, ...prev].slice(0, 200));
      } catch { /* ignore */ }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);

  const handleScenarioResult = (data: Transaction | object, scenarioId: string) => {
    // sita / sita_legit / mule_ring return a single verdict
    if ("transaction_id" in data) {
      const tx = data as Transaction;
      setTxs((prev) => [tx, ...prev].slice(0, 200));
      setSelected(tx);
    }
    // cold_start returns {legit, suspicious} — add both
    if ("legit" in data && "suspicious" in data) {
      const d = data as { legit: Transaction; suspicious: Transaction };
      setTxs((prev) => [d.suspicious, d.legit, ...prev].slice(0, 200));
      setSelected(d.suspicious);
    }
    // sim_swap returns {verdict, reason} — no transaction to show in stream
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white font-sans select-none">
      {/* Header */}
      <header className="border-b border-gray-800/80 px-6 py-3 flex items-center justify-between bg-gray-950/90 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <span className="text-xl font-black tracking-tight text-white">SENTINEL</span>
          <span className="text-xs text-gray-600 hidden sm:block">Agentic Fraud Detection · Global IME Hackathon 2026</span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          {/* Real P99 from /stats */}
          {stats && stats.total > 0 && (
            <span className="text-gray-400">
              P99{" "}
              <span className={`font-bold ${stats.p99_ms > 380 ? "text-red-400" : "text-emerald-400"}`}>
                {stats.p99_ms.toFixed(0)}ms
              </span>
            </span>
          )}
          <span
            className={`flex items-center gap-1 font-medium ${
              wsStatus === "open" ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {wsStatus === "open" ? <CheckCircle size={13} /> : <XCircle size={13} />}
            {wsStatus === "open" ? "Live" : "Reconnecting…"}
          </span>
        </div>
      </header>

      {/* Main grid: stream | inspector | right-column */}
      <div className="grid grid-cols-12 gap-3 p-3 h-[calc(100vh-49px)]">
        {/* Stream — col 1-3 */}
        <div className="col-span-3 bg-gray-900/60 border border-gray-800/60 rounded-xl p-3 overflow-hidden flex flex-col">
          <TransactionStream txs={txs} onSelect={setSelected} selected={selected} />
        </div>

        {/* Inspector — col 4-8 */}
        <div className="col-span-5 bg-gray-900/60 border border-gray-800/60 rounded-xl p-4 overflow-hidden">
          <TransactionInspector tx={selected} />
        </div>

        {/* Right column — col 9-12 */}
        <div className="col-span-4 flex flex-col gap-3 overflow-hidden">
          {/* Scenarios */}
          <div className="bg-gray-900/60 border border-gray-800/60 rounded-xl p-3 shrink-0">
            <ScenarioPanel onResult={handleScenarioResult} />
          </div>

          {/* OTP Interlock */}
          <div className="bg-gray-900/60 border border-gray-800/60 rounded-xl p-3 shrink-0">
            <OTPViewer />
          </div>

          {/* Stats */}
          <div className="bg-gray-900/60 border border-gray-800/60 rounded-xl p-3 flex-1 overflow-y-auto">
            <StatsPanel txs={txs} />
          </div>
        </div>
      </div>
    </div>
  );
}
