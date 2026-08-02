import catalogue from "@/data/workbenches.json";

export type Workbench = {
  id: number;
  category: string;
  short_category: string;
  evidence_lane: string;
  workbench: string;
  hard_gate_and_score: string;
  economic_or_physical_guardrail: string;
  benchmark: string;
  reference_url: string;
  starter_pack: string;
  track: string;
  implementation_status?: string;
  contract_version?: string;
  factory_path?: string;
  control_plane_path?: string;
  active_round?: string;
};

const raw = catalogue as { version: number; generated_at: string; workbenches: Workbench[] };

export const catalogueVersion = raw.version;
export const catalogueGeneratedAt = raw.generated_at;
export const workbenches = [...raw.workbenches].sort((a, b) => a.id - b.id);

export const categories = Array.from(
  new Map(
    workbenches.map((workbench) => [workbench.short_category, workbench.short_category]),
  ).values(),
).sort();

export function workbenchCode(id: number) {
  return `WB-${String(id).padStart(3, "0")}`;
}

export function getWorkbench(id: number) {
  return workbenches.find((workbench) => workbench.id === id) ?? null;
}

export function workbenchReadiness(workbench: Workbench) {
  return workbench.implementation_status === "pilot_round_open"
    ? "INSTRUMENTED TEST ARTICLE"
    : "BRIEF READY";
}

export function referenceLinks(reference: string) {
  return reference
    .split("|")
    .map((value) => value.trim())
    .filter(Boolean);
}

export const categoryCounts = categories.map((category) => ({
  category,
  count: workbenches.filter((workbench) => workbench.short_category === category)
    .length,
}));
