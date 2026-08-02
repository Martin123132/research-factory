import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";


function sha256(payload) {
  return createHash("sha256").update(payload).digest("hex");
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

function verifySelfHash(document, field, label) {
  const { [field]: claimed, ...body } = document;
  const actual = sha256(Buffer.from(JSON.stringify(canonicalize(body)), "utf8"));
  if (claimed !== actual) {
    throw new Error(`${label} ${field} mismatch: expected ${claimed}, calculated ${actual}`);
  }
}

const summaryBytes = await readFile(new URL("../data/workbench-contracts.json", import.meta.url));
const readinessBytes = await readFile(new URL("../data/workbench-readiness.json", import.meta.url));
const bundleBytes = await readFile(new URL("../public/workbench-contracts-v1.json", import.meta.url));
const schemaBytes = await readFile(new URL("../public/workbench-contract-v1.schema.json", import.meta.url));
const summary = JSON.parse(summaryBytes.toString("utf8"));
const readiness = JSON.parse(readinessBytes.toString("utf8"));
const bundle = JSON.parse(bundleBytes.toString("utf8"));
const schema = JSON.parse(schemaBytes.toString("utf8"));

verifySelfHash(summary, "summary_sha256", "Hangar contract snapshot");
verifySelfHash(readiness, "readiness_sha256", "Compact readiness snapshot");
verifySelfHash(bundle, "bundle_sha256", "Public contract bundle");

if (summary.standard !== "research-factory/workbench-contract/v1") {
  throw new Error(`Unexpected contract standard: ${summary.standard}`);
}
if (summary.schema_version !== 1 || bundle.schema_version !== 1) {
  throw new Error("Contract snapshot and bundle must use schema version 1.");
}
if (!/^[a-f0-9]{64}$/.test(summary.generator_sha256)) {
  throw new Error("The station-kit generator must be bound to a lowercase SHA-256 digest.");
}
if (summary.generator_sha256 !== bundle.generator_sha256) {
  throw new Error("Snapshot and public bundle generator digests disagree.");
}
if (summary.catalogue_sha256 !== bundle.catalogue_sha256) {
  throw new Error("Snapshot and public bundle catalogue digests disagree.");
}
if (readiness.catalogue_sha256 !== summary.catalogue_sha256 || readiness.standard !== summary.standard) {
  throw new Error("Compact readiness snapshot provenance disagrees with the contract snapshot.");
}
if (
  summary.stations?.length !== 100 ||
  readiness.stations?.length !== 100 ||
  bundle.contracts?.length !== 100
) {
  throw new Error("Exactly 100 station records and contracts are required.");
}
if (schema.title !== "Research Factory Workbench Contract v1" || schema.additionalProperties !== false) {
  throw new Error("The public Contract v1 schema is missing or not fail-closed at its root.");
}

const summaryByCode = new Map(summary.stations.map((station) => [station.workbench_code, station]));
const readinessByCode = new Map(readiness.stations.map((station) => [station.workbench_code, station]));
const stageCounts = { CONTRACT_DRAFT: 0, COMMISSIONING_READY: 0, LIVE_READY: 0 };
let runnableEntryGates = 0;
let liveResearch = 0;
const profileCounts = { ADAPTER_BOUND: 0, LEGACY_INSTRUMENTED: 0, CATALOGUE_ONLY: 0 };

bundle.contracts.forEach((contract, index) => {
  const numericId = index + 1;
  const code = `WB-${String(numericId).padStart(3, "0")}`;
  const station = summaryByCode.get(code);
  const compact = readinessByCode.get(code);
  if (!station || contract.workbench.code !== code || contract.workbench.numeric_id !== numericId) {
    throw new Error(`${code} is missing or its IDs disagree across snapshots.`);
  }
  if (
    !compact ||
    compact.numeric_id !== numericId ||
    compact.readiness_stage !== contract.readiness.current_stage
  ) {
    throw new Error(`${code} compact readiness record disagrees with its contract.`);
  }
  const contractSha256 = sha256(Buffer.from(JSON.stringify(canonicalize(contract)), "utf8"));
  if (station.contract_sha256 !== contractSha256) {
    throw new Error(`${code} contract digest does not match its public contract.`);
  }
  if (!(contract.readiness.current_stage in stageCounts)) {
    throw new Error(`${code} has an unsupported readiness stage.`);
  }
  stageCounts[contract.readiness.current_stage] += 1;
  if (!(contract.commissioning?.profile_status in profileCounts)) {
    throw new Error(`${code} has an unsupported commissioning profile.`);
  }
  profileCounts[contract.commissioning.profile_status] += 1;
  if (
    station.commissioning_profile !== contract.commissioning.profile_status ||
    station.adapter_id !== contract.commissioning.adapter_id ||
    station.adapter_version !== contract.commissioning.adapter_version
  ) {
    throw new Error(`${code} commissioning profile disagrees across snapshots.`);
  }
  if (
    contract.commissioning.profile_status === "ADAPTER_BOUND" &&
    (!contract.commissioning.adapter_id || !contract.commissioning.dossier_sha256)
  ) {
    throw new Error(`${code} is adapter-bound without a committed adapter dossier.`);
  }
  if (contract.starter_pack.fixture_status === "KNOWN_ANSWER_READY") runnableEntryGates += 1;
  if (contract.readiness.live_research_enabled) liveResearch += 1;
  if (
    contract.readiness.scientific_standing !== "NONE" ||
    contract.readiness.promotion_claims_allowed !== false ||
    station.scientific_evidence !== false ||
    station.counts_as_independent_reproduction !== false ||
    station.eligible_for_promotion !== false
  ) {
    throw new Error(`${code} improperly claims scientific or promotion credit.`);
  }
  if (
    contract.reproduction.required_independent_human_validators !== 2 ||
    contract.reproduction.author_may_validate !== false ||
    contract.reproduction.distinct_people_required !== true ||
    contract.reproduction.result_visibility !== "COMMIT_BEFORE_REVEAL" ||
    contract.disputes.majority_vote_can_promote !== false
  ) {
    throw new Error(`${code} violates the two-person blind-reproduction policy.`);
  }
});

const expectedCounts = {
  total: 100,
  contract_draft: stageCounts.CONTRACT_DRAFT,
  commissioning_ready: stageCounts.COMMISSIONING_READY,
  live_ready: stageCounts.LIVE_READY,
  runnable_entry_gate: runnableEntryGates,
  live_research_enabled: liveResearch,
  adapter_bound: profileCounts.ADAPTER_BOUND,
  legacy_instrumented: profileCounts.LEGACY_INSTRUMENTED,
  catalogue_only: profileCounts.CATALOGUE_ONLY,
};
if (JSON.stringify(summary.counts) !== JSON.stringify(expectedCounts)) {
  throw new Error(`Contract readiness counts disagree: ${JSON.stringify({ expectedCounts, actual: summary.counts })}`);
}

console.log(
  `Station kits verified: 100 contracts, ${stageCounts.COMMISSIONING_READY} commissioning-ready, ${liveResearch} live, snapshot ${summary.summary_sha256}`,
);
