import contractSnapshot from "@/data/workbench-contracts.json";
import type { WorkbenchContractStage } from "@/lib/workbenches";


export type WorkbenchContractSummary = {
  workbench_code: string;
  numeric_id: number;
  slug: string;
  title: string;
  contract_version: string;
  evidence_lane: string;
  kit_path: string;
  contract_path: string;
  contract_sha256: string;
  kit_sha256: string;
  readiness_stage: WorkbenchContractStage;
  starter_pack_status: "BRIEF_ONLY" | "KNOWN_ANSWER_READY";
  unresolved_count: number;
  unresolved: string[];
  facets: Record<string, boolean>;
  scientific_evidence: false;
  counts_as_independent_reproduction: false;
  eligible_for_promotion: false;
};

type ContractSnapshot = {
  schema_version: number;
  standard: string;
  generator_sha256: string;
  catalogue_sha256: string;
  station_kits_manifest_sha256: string;
  summary_sha256: string;
  counts: {
    total: number;
    contract_draft: number;
    commissioning_ready: number;
    live_ready: number;
    runnable_entry_gate: number;
    live_research_enabled: number;
  };
  stations: WorkbenchContractSummary[];
};

const contracts = contractSnapshot as ContractSnapshot;
const contractById = new Map(
  contracts.stations.map((contract) => [contract.numeric_id, contract]),
);

export const contractStandard = contracts.standard;
export const contractGeneratorSha256 = contracts.generator_sha256;
export const contractSnapshotSha256 = contracts.summary_sha256;
export const stationKitsManifestSha256 = contracts.station_kits_manifest_sha256;
export const contractCounts = contracts.counts;
export const workbenchContracts = [...contracts.stations].sort(
  (a, b) => a.numeric_id - b.numeric_id,
);

export function getWorkbenchContract(id: number) {
  return contractById.get(id) ?? null;
}
