import catalogue from "@/data/workbenches.json";
import readinessSnapshot from "@/data/workbench-readiness.json";

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

export type WorkbenchContractStage =
  | "CONTRACT_DRAFT"
  | "COMMISSIONING_READY"
  | "LIVE_READY";

type ReadinessSnapshot = {
  schema_version: number;
  standard: string;
  catalogue_sha256: string;
  readiness_sha256: string;
  stations: Array<{
    numeric_id: number;
    workbench_code: string;
    readiness_stage: WorkbenchContractStage;
  }>;
};

const readiness = readinessSnapshot as ReadinessSnapshot;
const readinessById = new Map(
  readiness.stations.map((station) => [station.numeric_id, station.readiness_stage]),
);

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
  const stage = readinessById.get(workbench.id);
  if (stage === "LIVE_READY") return "LIVE READY";
  if (stage === "COMMISSIONING_READY") return "COMMISSIONING READY";
  return "CONTRACT DRAFT";
}

export function workbenchStatusDot(workbench: Workbench) {
  const stage = readinessById.get(workbench.id);
  if (stage === "LIVE_READY") return "status-dot status-dot-green";
  if (stage === "COMMISSIONING_READY") return "status-dot status-dot-amber";
  return "status-dot";
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
