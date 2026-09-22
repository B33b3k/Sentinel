// Canonical scenario metadata, shared between the dashboard's scenario buttons and the landing
// page's feature list — see tests/scenarios/ for the actual fixtures (sita.py, sim_swap.py,
// cold_start.py, mule_ring.py) these describe.
export interface ScenarioMeta {
  id: string;
  label: string;
  desc: string;
}

export const SCENARIOS: ScenarioMeta[] = [
  { id: "sita", label: "Sita Attack", desc: "2am · NPR 85K · new device" },
  { id: "sita_legit", label: "Sita Legit", desc: "11am · NPR 1.2K · known device" },
  { id: "sim_swap", label: "SIM Swap", desc: "SMS ✓ Email ✗ → BLOCK" },
  { id: "cold_start", label: "Cold Start", desc: "Day-5 overseas worker" },
  { id: "mule_ring", label: "Mule Ring", desc: "5 sources → mule → dest" },
];
