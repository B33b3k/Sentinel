import {
  Shield, ArrowRight, Github, Zap, Network, ShieldAlert, Clock, Users,
  Layers, CheckCircle, AlertTriangle, XCircle, Smartphone, Mail, Database,
  Server, Boxes, GitBranch, FlaskConical,
} from "lucide-react";
import { SCENARIOS } from "./lib/scenarios";

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

const VERDICT_ROUTES = [
  {
    verdict: "ALLOW",
    icon: <CheckCircle size={18} />,
    color: "text-emerald-700",
    bg: "bg-emerald-50 border-emerald-200",
    threshold: "composite < 0.40",
    desc: "Transaction proceeds immediately — no added friction for the customer.",
  },
  {
    verdict: "OTP_INTERLOCK",
    icon: <AlertTriangle size={18} />,
    color: "text-amber-700",
    bg: "bg-amber-50 border-amber-200",
    threshold: "0.40 ≤ composite < 0.75",
    desc: "Transaction is frozen and a dual-path SMS + Email OTP challenge is fired.",
  },
  {
    verdict: "BLOCK",
    icon: <XCircle size={18} />,
    color: "text-red-700",
    bg: "bg-red-50 border-red-200",
    threshold: "composite ≥ 0.75",
    desc: "Transaction is rejected outright — composite score left no other option.",
  },
];

const OTP_OUTCOMES = [
  { sms: true, email: true, outcome: "RELEASE", note: "Both channels confirm — release the hold.", color: "text-emerald-700" },
  { sms: false, email: true, outcome: "BLOCK", note: "SMS fails, Email succeeds — the SIM-swap signal.", color: "text-red-700" },
  { sms: true, email: false, outcome: "HUMAN_REVIEW", note: "Email fails, SMS succeeds — escalate, don't auto-clear.", color: "text-amber-700" },
  { sms: false, email: false, outcome: "BLOCK", note: "Both channels fail — no path to verify the customer.", color: "text-red-700" },
];

const COHORTS = [
  "overseas_worker_remittance", "salary_kathmandu", "salary_other",
  "savings_urban", "savings_rural", "current_business",
];

const STACK = [
  { group: "Backend", icon: <Server size={16} />, items: ["Python 3.12", "FastAPI", "PyTorch", "scikit-learn"] },
  { group: "Infrastructure", icon: <Database size={16} />, items: ["Kafka", "Redis", "Neo4j", "PostgreSQL", "MLflow"] },
  { group: "Frontend", icon: <Layers size={16} />, items: ["React 18", "TypeScript", "Vite", "Tailwind", "Recharts"] },
  { group: "Quality", icon: <FlaskConical size={16} />, items: ["pytest", "Locust load tests", "Black + Ruff", "Docker Compose"] },
];

const REPO_URL = "https://github.com/B33b3k/Sentinel";

export default function Landing() {
  return (
    <div className="min-h-screen">
      <div className="max-w-5xl mx-auto px-6 py-16">
        {/* Hero */}
        <div className="glass rounded-2xl p-8 md:p-12 mb-8 animate-fade-in text-center">
          <div className="inline-flex p-4 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl shadow-md mb-6">
            <Shield size={36} className="text-white" />
          </div>
          <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-blue-700 to-indigo-700 bg-clip-text text-transparent mb-4">
            SENTINEL
          </h1>
          <p className="text-lg text-slate-700 max-w-2xl mx-auto mb-2">
            Multi-agent, real-time fraud detection for Nepal's banking sector.
          </p>
          <p className="text-sm text-slate-500 max-w-2xl mx-auto mb-8">
            Global IME AI/ML Hackathon 2026 · Track B — Security &amp; Fraud. A research/hackathon
            prototype, not a production banking system.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <a
              href="/demo"
              className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-700 hover:from-blue-500 hover:to-indigo-600 text-white font-semibold px-6 py-3 rounded-xl transition-all hover:scale-[1.02] active:scale-[0.98] shadow-sm"
            >
              Launch Live Demo <ArrowRight size={18} />
            </a>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 glass glass-hover text-slate-700 font-semibold px-6 py-3 rounded-xl transition-all"
            >
              <Github size={18} /> View source
            </a>
          </div>
          <p className="text-xs text-slate-400 mt-4">
            The demo above runs entirely in your browser on simulated transactions — no backend,
            no real account data.
          </p>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {METRICS.map((m) => (
            <div key={m.label} className="glass rounded-xl p-5 text-center">
              <div className="flex items-center justify-center gap-2 text-blue-600 mb-2">{m.icon}</div>
              <div className="text-2xl font-bold text-slate-900">{m.value}</div>
              <div className="text-xs text-slate-500 mt-1">{m.label}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">{m.note}</div>
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400 text-center mb-12">
          Reproducible from a committed benchmark run (<code className="bg-slate-100 px-1 py-0.5 rounded">scripts/benchmark_synthetic.py</code>) —
          see the repository's <code className="bg-slate-100 px-1 py-0.5 rounded">docs/07-performance.md</code> for method and the full numbers,
          including where detection quality falls short of the hackathon's stretch targets.
        </p>

        {/* How it works */}
        <div className="glass rounded-2xl p-8 mb-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-6 text-center">
            How a transaction is scored
          </h2>
          <div className="grid md:grid-cols-4 gap-4 mb-6">
            {AGENTS.map((a) => (
              <div key={a.name} className="glass rounded-xl p-4">
                <div className="text-sm font-bold text-blue-700 mb-1">{a.name}</div>
                <div className="text-xs text-slate-500 leading-relaxed">{a.desc}</div>
              </div>
            ))}
          </div>
          <p className="text-sm text-slate-600 text-center max-w-2xl mx-auto">
            All four agents score a transaction in parallel. A <span className="text-slate-900 font-medium">context-aware
            synthesis agent</span> combines them with weights that depend on transaction type — a
            SWIFT remittance weights the graph agent at 0.45 for mule detection; a QR payment weights
            geo/velocity higher instead.
          </p>
        </div>

        {/* Verdict routing */}
        <div className="glass rounded-2xl p-8 mb-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-6 text-center">
            Verdict routing
          </h2>
          <div className="grid md:grid-cols-3 gap-4 mb-6">
            {VERDICT_ROUTES.map((v) => (
              <div key={v.verdict} className={`rounded-xl border p-4 ${v.bg}`}>
                <div className={`flex items-center gap-2 font-bold mb-1 ${v.color}`}>
                  {v.icon} {v.verdict}
                </div>
                <div className="text-[11px] font-mono text-slate-500 mb-2">{v.threshold}</div>
                <div className="text-xs text-slate-600 leading-relaxed">{v.desc}</div>
              </div>
            ))}
          </div>

          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 text-center">
            OTP interlock — dual-path SMS + Email
          </h3>
          <p className="text-sm text-slate-600 text-center max-w-2xl mx-auto mb-4">
            An <span className="text-amber-700 font-medium">OTP_INTERLOCK</span> verdict freezes the
            transaction and sends two independent codes. The two channels resolving differently is
            itself a signal — a stolen SIM can intercept SMS but not the account's registered email.
          </p>
          <div className="grid sm:grid-cols-2 gap-3 max-w-2xl mx-auto">
            {OTP_OUTCOMES.map((o) => (
              <div key={o.outcome + o.sms + o.email} className="glass rounded-lg p-3 flex items-start gap-3">
                <div className="flex flex-col items-center gap-1 pt-0.5 text-xs shrink-0">
                  <span className="flex items-center gap-1 text-slate-400">
                    <Smartphone size={14} /> {o.sms ? <CheckCircle size={14} className="text-emerald-600" /> : <XCircle size={14} className="text-red-600" />}
                  </span>
                  <span className="flex items-center gap-1 text-slate-400">
                    <Mail size={14} /> {o.email ? <CheckCircle size={14} className="text-emerald-600" /> : <XCircle size={14} className="text-red-600" />}
                  </span>
                </div>
                <div>
                  <div className={`text-xs font-bold ${o.color}`}>{o.outcome}</div>
                  <div className="text-[11px] text-slate-500 leading-relaxed">{o.note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Demo scenarios */}
        <div className="glass rounded-2xl p-8 mb-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-6 text-center">
            Demo scenarios
          </h2>
          <div className="grid sm:grid-cols-2 md:grid-cols-5 gap-3">
            {SCENARIOS.map((s) => (
              <div key={s.id} className="glass rounded-xl p-4">
                <div className="text-sm font-bold text-blue-700 mb-1">{s.label}</div>
                <div className="text-xs text-slate-500 leading-relaxed">{s.desc}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400 text-center mt-4">
            Fire any of these from the live demo to see the full agent breakdown and verdict.
            Backed by fixtures in <code className="bg-slate-100 px-1 py-0.5 rounded text-slate-500">tests/scenarios/</code>.
          </p>
        </div>

        {/* Cohorts & cold start */}
        <div className="glass rounded-2xl p-8 mb-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-4 text-center">
            Cohorts &amp; cold start
          </h2>
          <p className="text-sm text-slate-600 text-center max-w-2xl mx-auto mb-4">
            Every account is assigned to one of six cohorts by first-match rules (account type +
            home district), each with its own trained LSTM and Isolation Forest. A brand-new account
            inherits its cohort's model from day one instead of scoring cold against a generic
            baseline.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {COHORTS.map((c) => (
              <span key={c} className="text-xs font-mono px-3 py-1.5 glass rounded-lg text-slate-600">
                {c}
              </span>
            ))}
          </div>
        </div>

        {/* Tech stack */}
        <div className="glass rounded-2xl p-8 mb-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-6 text-center">
            Built with
          </h2>
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-4">
            {STACK.map((s) => (
              <div key={s.group} className="glass rounded-xl p-4">
                <div className="flex items-center gap-2 text-blue-700 font-bold text-sm mb-2">
                  {s.icon} {s.group}
                </div>
                <ul className="space-y-1">
                  {s.items.map((item) => (
                    <li key={item} className="text-xs text-slate-500">{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400 text-center mt-4 flex items-center justify-center gap-1.5">
            <GitBranch size={12} /> Full justification for each choice in{" "}
            <code className="bg-slate-100 px-1 py-0.5 rounded text-slate-500">docs/03-tech-stack.md</code>.
          </p>
        </div>

        {/* Repo pointer */}
        <div className="glass rounded-2xl p-6 mb-8 flex flex-wrap items-center justify-center gap-2 text-sm text-slate-600">
          <Boxes size={16} className="text-purple-600" />
          Eight Docker services orchestrate the full stack — Kafka, Redis, Neo4j, Postgres, MLflow,
          the orchestrator API, and this dashboard. See{" "}
          <code className="bg-slate-100 px-1 py-0.5 rounded text-slate-500">docs/02-architecture.md</code> for the request flow end to end.
        </div>

        <footer className="text-center text-xs text-slate-400 pb-8">
          Built for the Global IME AI/ML Hackathon 2026, Track B. All performance figures on this
          page are from a committed, reproducible benchmark — not hand-set.
        </footer>
      </div>
    </div>
  );
}
