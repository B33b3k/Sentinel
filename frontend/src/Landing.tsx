import { Shield, ArrowRight, Github, Zap, Network, ShieldAlert, Clock } from "lucide-react";

const METRICS = [
  { label: "P99 latency", value: "18.9 ms", note: "measured, 800 ms budget", icon: <Clock size={18} /> },
  { label: "Detection AUROC", value: "0.742", note: "vs. 0.71 rule-engine baseline", icon: <ShieldAlert size={18} /> },
  { label: "Agents", value: "4 parallel", note: "velocity · geo · behavior · GNN", icon: <Network size={18} /> },
  { label: "Tests passing", value: "96", note: "pytest, reproducible", icon: <Zap size={18} /> },
];

const AGENTS = [
  { name: "Velocity", desc: "Redis sliding-window transaction-rate counters — catches bursts, structuring, dormancy breaks." },
  { name: "Geo", desc: "Geo-velocity & device fingerprint heuristics — impossible travel, new device, SIM change." },
  { name: "Behavior", desc: "Per-cohort LSTM + Isolation Forest ensemble — amount, timing, counterparty anomalies." },
  { name: "GNN", desc: "Neo4j Cypher graph queries — money-mule rings and layering, degrades gracefully if graph is down." },
];

const REPO_URL = "https://github.com/B33b3k/Sentinel";

export default function Landing() {
  return (
    <div className="min-h-screen">
      <div className="max-w-5xl mx-auto px-6 py-16">
        {/* Hero */}
        <div className="glass rounded-2xl p-8 md:p-12 mb-8 animate-fade-in text-center">
          <div className="inline-flex p-4 bg-gradient-to-br from-blue-600 to-purple-600 rounded-2xl shadow-lg mb-6">
            <Shield size={36} className="text-white" />
          </div>
          <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent mb-4">
            SENTINEL
          </h1>
          <p className="text-lg text-gray-300 max-w-2xl mx-auto mb-2">
            Multi-agent, real-time fraud detection for Nepal's banking sector.
          </p>
          <p className="text-sm text-gray-500 max-w-2xl mx-auto mb-8">
            Global IME AI/ML Hackathon 2026 · Track B — Security &amp; Fraud. A research/hackathon
            prototype, not a production banking system.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <a
              href="/demo"
              className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-semibold px-6 py-3 rounded-xl transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              Launch Live Demo <ArrowRight size={18} />
            </a>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 glass glass-hover text-gray-200 font-semibold px-6 py-3 rounded-xl transition-all"
            >
              <Github size={18} /> View source
            </a>
          </div>
          <p className="text-xs text-gray-600 mt-4">
            The demo above runs entirely in your browser on simulated transactions — no backend,
            no real account data.
          </p>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {METRICS.map((m) => (
            <div key={m.label} className="glass rounded-xl p-5 text-center">
              <div className="flex items-center justify-center gap-2 text-blue-400 mb-2">{m.icon}</div>
              <div className="text-2xl font-bold text-white">{m.value}</div>
              <div className="text-xs text-gray-400 mt-1">{m.label}</div>
              <div className="text-[11px] text-gray-600 mt-0.5">{m.note}</div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 text-center mb-12">
          Reproducible from a committed benchmark run (<code>scripts/benchmark_synthetic.py</code>) —
          see the repository's <code>docs/07-performance.md</code> for method and the full numbers,
          including where detection quality falls short of the hackathon's stretch targets.
        </p>

        {/* How it works */}
        <div className="glass rounded-2xl p-8 mb-8">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-6 text-center">
            How a transaction is scored
          </h2>
          <div className="grid md:grid-cols-4 gap-4 mb-6">
            {AGENTS.map((a) => (
              <div key={a.name} className="glass rounded-xl p-4">
                <div className="text-sm font-bold text-blue-300 mb-1">{a.name}</div>
                <div className="text-xs text-gray-400 leading-relaxed">{a.desc}</div>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-400 text-center max-w-2xl mx-auto">
            All four agents score a transaction in parallel. A <span className="text-gray-200 font-medium">context-aware
            synthesis agent</span> combines them with weights that depend on transaction type — a
            SWIFT remittance weights the graph agent at 0.45 for mule detection; a QR payment weights
            geo/velocity higher instead. The composite score routes to <span className="text-emerald-400 font-medium">ALLOW</span>,{" "}
            <span className="text-amber-400 font-medium">OTP_INTERLOCK</span>, or{" "}
            <span className="text-red-400 font-medium">BLOCK</span> — suspicious transactions get a
            dual-path SMS+Email OTP challenge designed to expose SIM-swap attacks, rather than an
            outright block.
          </p>
        </div>

        <footer className="text-center text-xs text-gray-600 pb-8">
          Built for the Global IME AI/ML Hackathon 2026, Track B. All performance figures on this
          page are from a committed, reproducible benchmark — not hand-set.
        </footer>
      </div>
    </div>
  );
}
