import { useState, useEffect, Component, type ReactNode } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from "recharts";
import {
  AlertTriangle, CheckCircle, XCircle, Zap, RefreshCw,
  ShieldAlert, Users, Globe, Activity, Shield, Clock, TrendingUp,
} from "lucide-react";
import { DEMO_MODE, getStats, runScenario, getPendingOTP, subscribeStream, StreamStatus } from "./lib/backend";
import type { Transaction, Stats, OTPPending, Verdict } from "./lib/mock";
import { SCENARIOS as BASE_SCENARIOS } from "./lib/scenarios";

const VERDICT_CONFIG: Record<Verdict, { color: string; bg: string; icon: JSX.Element; glow: string }> = {
  ALLOW: {
    color: "text-emerald-700",
    bg: "bg-emerald-50 border-emerald-200",
    icon: <CheckCircle size={16} />,
    glow: "glow-emerald",
  },
  OTP_INTERLOCK: {
    color: "text-amber-700",
    bg: "bg-amber-50 border-amber-200",
    icon: <AlertTriangle size={16} />,
    glow: "glow-amber",
  },
  BLOCK: {
    color: "text-red-700",
    bg: "bg-red-50 border-red-200",
    icon: <XCircle size={16} />,
    glow: "glow-red",
  },
};

const CHART_COLORS = ["#059669", "#d97706", "#dc2626", "#2563eb", "#7c3aed"];

// ─── PanelBoundary ────────────────────────────────────────────────────────────
// Isolates a panel's render/runtime errors so one bad response (e.g. a stale
// backend, a network blip) can't blank the entire dashboard.
class PanelBoundary extends Component<{ label: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error(`[${this.props.label}] panel crashed:`, error);
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="glass rounded-2xl p-5 flex items-center justify-center h-full min-h-[120px]">
          <div className="text-center text-slate-400">
            <AlertTriangle size={24} className="mx-auto mb-2 opacity-50" />
            <p className="text-xs">{this.props.label} is unavailable right now</p>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const SCENARIO_STYLE: Record<string, { icon: JSX.Element; color: string }> = {
  sita: { icon: <ShieldAlert size={14} />, color: "bg-red-600 hover:bg-red-500" },
  sita_legit: { icon: <CheckCircle size={14} />, color: "bg-emerald-600 hover:bg-emerald-500" },
  sim_swap: { icon: <AlertTriangle size={14} />, color: "bg-orange-600 hover:bg-orange-500" },
  cold_start: { icon: <Users size={14} />, color: "bg-blue-600 hover:bg-blue-500" },
  mule_ring: { icon: <Globe size={14} />, color: "bg-purple-600 hover:bg-purple-500" },
};

const SCENARIOS = BASE_SCENARIOS.map((s) => ({ ...s, ...SCENARIO_STYLE[s.id] }));

// ─── Header ───────────────────────────────────────────────────────────────────
function Header({ stats, wsStatus }: { stats: Stats | null; wsStatus: string }) {
  const statusColor = wsStatus === "open" ? "bg-emerald-500" : wsStatus === "connecting" ? "bg-amber-500" : "bg-red-500";
  const statusIcon = wsStatus === "open" ? "●" : wsStatus === "connecting" ? "◐" : "○";

  return (
    <div className="glass rounded-2xl p-6 mb-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-xl shadow-md">
            <Shield size={28} className="text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text text-transparent">
              SENTINEL
            </h1>
            <p className="text-sm text-slate-500">Real-Time Fraud Detection · Multi-Agent ML System</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-6">
          {stats && (
            <>
              <div className="text-right">
                <div className="text-2xl font-bold text-slate-900">{stats.p99_ms.toFixed(0)}ms</div>
                <div className="text-xs text-slate-500 flex items-center gap-1 justify-end">
                  <Clock size={12} /> P99 Latency
                </div>
                <div className="text-xs text-emerald-600 font-semibold">
                  {((stats.p99_ms / 800) * 100).toFixed(0)}% of budget
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-slate-900">{stats.total}</div>
                <div className="text-xs text-slate-500 flex items-center gap-1 justify-end">
                  <Activity size={12} /> Transactions
                </div>
                <div className="text-xs text-blue-600 font-semibold">
                  {stats.allow + stats.otp_interlock + stats.block > 0
                    ? `${((stats.block / (stats.allow + stats.otp_interlock + stats.block)) * 100).toFixed(1)}% blocked`
                    : "0% blocked"}
                </div>
              </div>
            </>
          )}
          <div className="flex items-center gap-2 px-3 py-2 glass rounded-lg">
            <div className={`w-2 h-2 rounded-full ${statusColor} animate-pulse`} />
            <span className="text-xs text-slate-600 uppercase tracking-wider font-semibold">{statusIcon} {wsStatus}</span>
          </div>
        </div>
      </div>

      {/* Processing Pipeline Visualization */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 pt-4 border-t border-slate-200">
        <div className="flex flex-wrap items-center gap-2">
          <div className="px-2 py-1 bg-blue-50 rounded border border-blue-200 text-blue-700">
            Kafka Stream
          </div>
          <span>→</span>
          <div className="px-2 py-1 bg-purple-50 rounded border border-purple-200 text-purple-700">
            4 Agents Parallel
          </div>
          <span>→</span>
          <div className="px-2 py-1 bg-amber-50 rounded border border-amber-200 text-amber-700">
            Synthesis
          </div>
          <span>→</span>
          <div className="px-2 py-1 bg-emerald-50 rounded border border-emerald-200 text-emerald-700">
            Verdict
          </div>
        </div>
        <div className="text-slate-500">
          {stats ? (
            <>
              Target: &lt;800ms · Achieved: {stats.p99_ms.toFixed(0)}ms ·{" "}
              <span className="text-emerald-600 font-semibold">
                {(((800 - stats.p99_ms) / 800) * 100).toFixed(0)}% faster
              </span>
            </>
          ) : (
            "Target: <800ms · Achieved: waiting for backend…"
          )}
        </div>
      </div>
    </div>
  );
}

// ─── TransactionStream ────────────────────────────────────────────────────────
function TransactionStream({ txs, onSelect, selected }: {
  txs: Transaction[];
  onSelect: (t: Transaction) => void;
  selected: Transaction | null;
}) {
  return (
    <div className="glass rounded-2xl p-5 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-4">
        <Activity size={18} className="text-blue-600" />
        <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">Live Stream</h2>
        <div className="ml-auto text-xs text-slate-400">{txs.length} transactions</div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-thin">
        {txs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-slate-300">
            <Activity size={32} className="mb-2 opacity-50" />
            <p className="text-xs">Waiting for transactions…</p>
          </div>
        )}
        {txs.map((tx) => {
          const config = VERDICT_CONFIG[tx.verdict];
          return (
            <button
              key={tx.transaction_id}
              onClick={() => onSelect(tx)}
              className={`w-full text-left rounded-xl border px-4 py-3 transition-all duration-200 animate-slide-in ${config.bg} ${
                selected?.transaction_id === tx.transaction_id
                  ? `ring-2 ring-indigo-400 ${config.glow}`
                  : "opacity-90 hover:opacity-100 glass-hover"
              }`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-mono text-xs text-slate-500 truncate max-w-[120px]">{tx.account_id}</span>
                <div className={`flex items-center gap-1 font-bold text-xs ${config.color}`}>
                  {config.icon}
                  {tx.verdict}
                </div>
              </div>
              <div className="flex justify-between text-xs text-slate-400">
                <span>{tx.transaction_type}</span>
                <span>{tx.total_latency_ms.toFixed(0)}ms</span>
              </div>
              <div className="mt-2 h-1 bg-slate-200 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    tx.verdict === "ALLOW" ? "bg-emerald-500" :
                    tx.verdict === "OTP_INTERLOCK" ? "bg-amber-500" : "bg-red-500"
                  }`}
                  style={{ width: `${Math.min(tx.composite_score * 100, 100)}%` }}
                />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── TransactionInspector ─────────────────────────────────────────────────────
function TransactionInspector({ tx }: { tx: Transaction | null }) {
  if (!tx) {
    return (
      <div className="glass rounded-2xl p-5 flex items-center justify-center h-full">
        <div className="text-center text-slate-300">
          <Zap size={48} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">Select a transaction to inspect</p>
        </div>
      </div>
    );
  }

  const config = VERDICT_CONFIG[tx.verdict];
  const agentData = tx.agent_scores.map((s) => ({
    name: s.agent.toUpperCase(),
    score: (s.score * 100).toFixed(1),
    fill: s.score > 0.75 ? "#dc2626" : s.score > 0.4 ? "#d97706" : "#059669",
  }));

  return (
    <div className="glass rounded-2xl p-5 flex flex-col h-full overflow-y-auto scrollbar-thin">
      <div className="flex items-center gap-2 mb-4">
        <Zap size={18} className="text-purple-600" />
        <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">Transaction Inspector</h2>
      </div>

      {/* Verdict Badge */}
      <div className={`rounded-xl border p-4 mb-4 ${config.bg} ${config.glow}`}>
        <div className="flex items-center justify-between mb-2">
          <div className={`flex items-center gap-2 text-lg font-bold ${config.color}`}>
            {config.icon}
            {tx.verdict}
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-slate-900">{(tx.composite_score * 100).toFixed(1)}%</div>
            <div className="text-xs text-slate-500">Risk Score</div>
          </div>
        </div>
        <div className="text-xs text-slate-500 font-mono">{tx.transaction_id}</div>
      </div>

      {/* Latency Breakdown */}
      <div className="mb-4">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Latency Breakdown · Total: {tx.total_latency_ms.toFixed(0)}ms
        </h3>
        <div className="space-y-2">
          {tx.agent_scores.map((s) => (
            <div key={s.agent} className="flex items-center gap-2">
              <div className="w-20 text-xs text-slate-500 uppercase">{s.agent}</div>
              <div className="flex-1 h-6 bg-slate-100 rounded-full overflow-hidden relative">
                <div
                  className="h-full bg-gradient-to-r from-blue-600 to-indigo-600 transition-all duration-500"
                  style={{ width: `${(s.latency_ms / tx.total_latency_ms) * 100}%` }}
                />
                <div className="absolute inset-0 flex items-center justify-center text-xs font-semibold text-slate-700">
                  {s.latency_ms.toFixed(0)}ms
                </div>
              </div>
              <div className="w-12 text-xs text-slate-400 text-right">
                {((s.latency_ms / tx.total_latency_ms) * 100).toFixed(0)}%
              </div>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-2 border-t border-slate-200">
            <div className="w-20 text-xs text-slate-500 uppercase">Budget</div>
            <div className="flex-1 h-6 bg-slate-100 rounded-full overflow-hidden relative">
              <div
                className={`h-full transition-all duration-500 ${
                  tx.total_latency_ms < 400 ? "bg-emerald-600" :
                  tx.total_latency_ms < 600 ? "bg-amber-600" : "bg-red-600"
                }`}
                style={{ width: `${(tx.total_latency_ms / 800) * 100}%` }}
              />
              <div className="absolute inset-0 flex items-center justify-center text-xs font-semibold text-slate-700">
                {((tx.total_latency_ms / 800) * 100).toFixed(0)}% of 800ms
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Agent Scores */}
      <div className="mb-4">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Agent Scores</h3>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={agentData} layout="vertical">
            <XAxis type="number" domain={[0, 100]} stroke="#94a3b8" fontSize={10} />
            <YAxis type="category" dataKey="name" stroke="#94a3b8" fontSize={10} width={80} />
            <Tooltip
              contentStyle={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px" }}
              labelStyle={{ color: "#1e293b" }}
            />
            <Bar dataKey="score" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Weights Used */}
      <div className="mb-4">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Context Weights</h3>
        <div className="grid grid-cols-4 gap-2">
          {Object.entries(tx.weights_used).map(([agent, weight]) => (
            <div key={agent} className="glass rounded-lg p-2 text-center">
              <div className="text-xs text-slate-400 uppercase">{agent}</div>
              <div className="text-lg font-bold text-slate-900">{(weight * 100).toFixed(0)}%</div>
            </div>
          ))}
        </div>
      </div>

      {/* Reason Codes */}
      <div>
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Reason Codes</h3>
        <div className="space-y-2">
          {tx.agent_scores.map((s) => (
            <div key={s.agent} className="glass rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-slate-600 uppercase">{s.agent}</span>
                <span className="text-xs text-slate-400">{s.latency_ms.toFixed(0)}ms</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {s.reason_codes.map((code, i) => (
                  <span key={i} className="text-xs px-2 py-0.5 bg-slate-100 text-slate-500 rounded">
                    {code}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── ScenarioPanel ────────────────────────────────────────────────────────────
function ScenarioPanel({ onResult }: { onResult: (t: Transaction | object, scenarioId: string) => void }) {
  const [loading, setLoading] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { verdict?: string; composite_score?: number } | null>>({});

  const fire = async (id: string) => {
    setLoading(id);
    try {
      const data = await runScenario(id);
      setResults((prev) => ({ ...prev, [id]: data }));
      onResult(data, id);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <ShieldAlert size={18} className="text-red-600" />
        <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">Demo Scenarios</h2>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {SCENARIOS.map((s) => {
          const result = results[s.id];
          return (
            <button
              key={s.id}
              onClick={() => fire(s.id)}
              disabled={loading === s.id}
              className={`${s.color} text-white rounded-xl px-4 py-3 text-left transition-all duration-200 disabled:opacity-50 hover:scale-[1.02] active:scale-[0.98] shadow-sm`}
            >
              <div className="flex items-center gap-2 mb-1">
                {loading === s.id ? <RefreshCw size={14} className="animate-spin" /> : s.icon}
                <span className="font-semibold text-sm">{s.label}</span>
              </div>
              <div className="text-xs opacity-90">{s.desc}</div>
              {result && (
                <div className="mt-2 text-xs font-mono bg-black/15 rounded px-2 py-1">
                  {result.verdict} · {((result.composite_score || 0) * 100).toFixed(1)}%
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── OTPViewer ────────────────────────────────────────────────────────────────
function OTPViewer() {
  const [pending, setPending] = useState<OTPPending[]>([]);

  useEffect(() => {
    const poll = async () => {
      try {
        setPending(await getPendingOTP());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <AlertTriangle size={18} className="text-amber-600" />
        <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">OTP Interlock</h2>
        <div className="ml-auto text-xs text-slate-400">{pending.length} pending</div>
      </div>

      {pending.length === 0 ? (
        <div className="text-center text-slate-300 py-8">
          <CheckCircle size={32} className="mx-auto mb-2 opacity-50" />
          <p className="text-xs">No pending OTP verifications</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-[200px] overflow-y-auto scrollbar-thin">
          {pending.map((otp) => (
            <div key={otp.tx_id} className="glass rounded-lg p-3 border border-amber-200 bg-amber-50/50">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs text-slate-500">{otp.account_id}</span>
                <span className="text-xs text-amber-700 font-semibold">PENDING</span>
              </div>
              <div className="text-xs text-slate-500 space-y-1">
                <div>📱 {otp.phone}</div>
                <div>📧 {otp.email}</div>
              </div>
            </div>
          ))}
        </div>
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
        setStats(await getStats());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, []);

  if (!stats) {
    return (
      <div className="glass rounded-2xl p-5 flex items-center justify-center h-full min-h-[160px]">
        <div className="text-center text-slate-300">
          <TrendingUp size={32} className="mx-auto mb-2 opacity-50" />
          <p className="text-xs">Waiting for stats from the backend…</p>
        </div>
      </div>
    );
  }

  const fraudByType = Object.entries(stats.fraud_by_type || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const verdictData = [
    { name: "ALLOW", value: stats.allow, fill: "#059669" },
    { name: "OTP", value: stats.otp_interlock, fill: "#d97706" },
    { name: "BLOCK", value: stats.block, fill: "#dc2626" },
  ];

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp size={18} className="text-blue-600" />
        <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">System Performance</h2>
      </div>

      {/* Real-time TPS */}
      <div className="mb-4 glass rounded-lg p-4 border border-blue-100 bg-blue-50/50">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500 uppercase">Throughput</span>
          <Activity size={14} className="text-blue-600 animate-pulse" />
        </div>
        <div className="text-3xl font-bold text-slate-900 mb-1">
          {txs.length > 0 ? Math.floor(txs.length / 10) : 0} <span className="text-lg text-slate-400">TPS</span>
        </div>
        <div className="text-xs text-slate-500">Transactions per second</div>
      </div>

      {/* Latency Metrics */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {(["p50_ms", "p95_ms", "p99_ms"] as const).map((k) => {
          const value = stats[k];
          const label = k.replace("_ms", "").toUpperCase();
          const color = value < 200 ? "text-emerald-600" : value < 400 ? "text-amber-600" : "text-red-600";
          return (
            <div key={k} className="glass rounded-lg p-3 text-center">
              <div className="text-xs text-slate-400 uppercase mb-1">{label}</div>
              <div className={`text-xl font-bold ${color}`}>{value.toFixed(0)}<span className="text-xs">ms</span></div>
              <div className="text-xs text-slate-400 mt-1">
                {((value / 800) * 100).toFixed(0)}% budget
              </div>
            </div>
          );
        })}
      </div>

      {/* Performance Target */}
      <div className="mb-4 glass rounded-lg p-3 border border-emerald-100 bg-emerald-50/50">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500 uppercase">Target: &lt; 800ms</span>
          <CheckCircle size={14} className="text-emerald-600" />
        </div>
        <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-emerald-600 to-blue-600 transition-all duration-500"
            style={{ width: `${Math.min((stats.p99_ms / 800) * 100, 100)}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-400 mt-1">
          <span>0ms</span>
          <span className="font-semibold text-emerald-600">{stats.p99_ms.toFixed(0)}ms</span>
          <span>800ms</span>
        </div>
      </div>

      {/* Verdict Distribution */}
      <div className="mb-4">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Verdict Distribution</h3>
        <ResponsiveContainer width="100%" height={150}>
          <PieChart>
            <Pie data={verdictData} dataKey="value" cx="50%" cy="50%" outerRadius={60} label>
              {verdictData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "8px" }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="grid grid-cols-3 gap-2 mt-2">
          <div className="text-center">
            <div className="text-lg font-bold text-emerald-600">{stats.allow}</div>
            <div className="text-xs text-slate-400">ALLOW</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-amber-600">{stats.otp_interlock}</div>
            <div className="text-xs text-slate-400">OTP</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold text-red-600">{stats.block}</div>
            <div className="text-xs text-slate-400">BLOCK</div>
          </div>
        </div>
      </div>

      {/* Fraud by Type */}
      {fraudByType.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Fraud Detected</h3>
          <div className="space-y-1">
            {fraudByType.map((item) => (
              <div key={item.name} className="flex items-center justify-between text-xs glass rounded px-2 py-1">
                <span className="text-slate-500">{item.name}</span>
                <span className="font-semibold text-red-600">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [wsStatus, setWsStatus] = useState<StreamStatus>("connecting");
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        setStats(await getStats());
      } catch {}
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeStream(
      (tx) => setTxs((prev) => [tx, ...prev].slice(0, 50)),
      setWsStatus,
    );
    return unsubscribe;
  }, []);

  const handleScenarioResult = (data: Transaction | object, scenarioId: string) => {
    if ("transaction_id" in data) {
      setTxs((prev) => [data as Transaction, ...prev].slice(0, 50));
      setSelected(data as Transaction);
    }
  };

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-[1800px] mx-auto">
        {DEMO_MODE && (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-700">
            Demo mode — transactions below are simulated in your browser (no backend, no real
            data). <a href="/" className="underline hover:text-amber-900">Back to overview</a>
          </div>
        )}
        <PanelBoundary label="Header">
          <Header stats={stats} wsStatus={wsStatus} />
        </PanelBoundary>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          {/* Left Column */}
          <div className="md:col-span-3 space-y-6">
            <PanelBoundary label="Demo scenarios">
              <ScenarioPanel onResult={handleScenarioResult} />
            </PanelBoundary>
            <PanelBoundary label="OTP interlock">
              <OTPViewer />
            </PanelBoundary>
          </div>

          {/* Middle Column */}
          <div className="md:col-span-4 h-[70vh] md:h-[calc(100vh-180px)]">
            <PanelBoundary label="Live stream">
              <TransactionStream txs={txs} onSelect={setSelected} selected={selected} />
            </PanelBoundary>
          </div>

          {/* Right Column */}
          <div className="md:col-span-5 space-y-6">
            <div className="h-[70vh] md:h-[calc(60vh-120px)]">
              <PanelBoundary label="Transaction inspector">
                <TransactionInspector tx={selected} />
              </PanelBoundary>
            </div>
            <div className="h-[70vh] md:h-[calc(40vh-120px)]">
              <PanelBoundary label="System performance">
                <StatsPanel txs={txs} />
              </PanelBoundary>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
