import type { Metadata } from "next";
import Link from "next/link";
import { ScopeNotice } from "@/components/ScopeNotice";
import {
  contractCounts,
  contractGeneratorSha256,
  contractSnapshotSha256,
  contractStandard,
  contractVersion,
  stationKitsManifestSha256,
  workbenchContracts,
} from "@/lib/workbench-contracts";

export const metadata: Metadata = {
  title: "Workbench Contract v1",
  description: "The fail-closed evidence and commissioning standard for all 100 Research Factory stations.",
};

const invariants = [
  ["01", "Objective truth", "Each station must define the input population, required output, locked independent verifier and exact pass rule. A candidate's own claim is never authoritative."],
  ["02", "Hard gates fail closed", "Missing evidence, malformed output, verifier errors and timeouts fail the gate. A good aggregate score cannot cancel failed correctness or safety."],
  ["03", "Task-specific tolerances", "Exact bytes, hashes and proofs use zero tolerance. Statistical or physical work declares repetitions, seeds, aggregation, confidence and runner class."],
  ["04", "Two other humans", "Exactly two distinct accountable humans reproduce the locked claim. The author cannot validate their own work and one person cannot occupy both identities."],
  ["05", "Blind before reveal", "Both validators commit conclusions and evidence hashes before either result is revealed. A deterministic split opens diagnosis and human review, never majority promotion."],
  ["06", "Failures remain useful", "Negative and disputed work stays append-only and searchable with its explored region, decisive boundary and conditions for revisiting it."],
  ["07", "Rights without takeover", "Contributors retain the rights they lawfully hold. The Factory records provenance and declarations but cannot certify ownership, inventorship, patentability or freedom to operate."],
] as const;

export default function StandardsPage() {
  const exactProofStations = workbenchContracts.filter(
    (contract) => contract.evidence_lane === "EXACT_PROOF",
  );
  const adapterBoundStations = workbenchContracts.filter(
    (contract) => contract.commissioning_profile === "ADAPTER_BOUND",
  );
  const adapterFamilies = new Set(
    adapterBoundStations.flatMap((contract) => contract.adapter_id ? [contract.adapter_id] : []),
  );

  return (
    <>
      <section className="page-heading-row standards-heading">
        <div className="page-heading">
          <p className="eyebrow">Factory standard / version {contractVersion}</p>
          <h1>A station does not become science because its folder exists.</h1>
          <p>
            Workbench Contract v1 is the gate between a promising problem brief and a laboratory
            that can accept reproducible work. It is deliberately strict about truth and
            deliberately neutral about credentials.
          </p>
        </div>
        <div className="page-status-card standards-readout">
          <span className="mono">CONTRACT SNAPSHOT</span>
          <strong>{contractCounts.total}</strong>
          <p>deterministic construction kits</p>
          <dl>
            <div><dt>Draft</dt><dd>{contractCounts.contract_draft}</dd></div>
            <div><dt>Commissioning</dt><dd>{contractCounts.commissioning_ready}</dd></div>
            <div><dt>Live</dt><dd>{contractCounts.live_ready}</dd></div>
          </dl>
        </div>
      </section>

      <ScopeNotice compact />

      <section className="section-block">
        <div className="section-heading">
          <div><p className="eyebrow">Non-negotiable invariants</p><h2>One evidence standard, fitted to each task</h2></div>
        </div>
        <div className="standard-invariant-grid">
          {invariants.map(([number, title, body]) => (
            <article key={number}>
              <span className="mono">{number}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block standard-stage-section">
        <div className="section-heading">
          <div><p className="eyebrow">Readiness, not theatre</p><h2>Three stages with different authority</h2></div>
        </div>
        <div className="standard-stage-grid">
          <article>
            <span className="stage-number mono">{String(contractCounts.contract_draft).padStart(2, "0")}</span>
            <p className="eyebrow">Contract draft</p>
            <h3>The target is mapped</h3>
            <p>The brief, references and governance exist. Missing datasets, formulas, verifiers or runners are named explicitly. No live submission is accepted.</p>
          </article>
          <article className="stage-commissioning">
            <span className="stage-number mono">{String(contractCounts.commissioning_ready).padStart(2, "0")}</span>
            <p className="eyebrow">Commissioning ready</p>
            <h3>The plumbing can be tested</h3>
            <p>WB-001 has frozen public inputs, a verifier, runner protocol, starter gate and local blind workflow. Its timing and identity boundaries are still not promotion-grade.</p>
          </article>
          <article className="stage-locked">
            <span className="stage-number mono">{String(contractCounts.live_ready).padStart(2, "0")}</span>
            <p className="eyebrow">Live ready</p>
            <h3>Locked by design</h3>
            <p>External identity, a central blind evaluator, promotion-grade isolated execution and explicit authorization must all exist before this count can move.</p>
          </article>
        </div>
      </section>

      <section className="section-block split-section standards-split">
        <article className="feature-card feature-card-orange">
          <p className="eyebrow">Commissioning adapters / closed families</p>
          <h2>{adapterBoundStations.length} stations across {adapterFamilies.size} bounded families</h2>
          <p>
            WB-002 uses <span className="mono">DIGITAL_COMPRESSION_V1</span>: a closed dossier,
            allowlisted adapter, hashed operational assets, exact restoration rules and a runnable
            entry fixture. WB-013 uses <span className="mono">DIGITAL_OPTIMIZATION_V1</span> with
            only <span className="mono">SYMMETRIC_TSP_V1</span> enabled. Both remain contract drafts;
            their official inputs, complete scorers and promotion boundaries are not frozen.
          </p>
          <div className="button-row">
            <Link className="text-link" href="/workbenches/2">Inspect WB-002 →</Link>
            <Link className="text-link" href="/workbenches/13">Inspect WB-013 →</Link>
          </div>
        </article>
        <article className="feature-card">
          <p className="eyebrow">Visible construction progress</p>
          <h2>{contractCounts.runnable_entry_gate} runnable entry gates</h2>
          <p>
            One is the legacy WB-001 test article; WB-002 and WB-013 add adapter-bound method gates.
            Passing any of them demonstrates careful procedure only: it creates no scientific
            evidence, independent reproduction or promotion credit.
          </p>
        </article>
      </section>

      <section className="section-block standard-flow-section">
        <div className="section-heading">
          <div><p className="eyebrow">Replication route</p><h2>A claim cannot inspect its own answer sheet</h2></div>
        </div>
        <div className="standard-flow" aria-label="Blind two-person reproduction flow">
          <article><span>1</span><strong>Author locks claim</strong><p>Artifact, inputs, method, environment and contract are content-addressed.</p></article>
          <i>→</i>
          <article><span>2</span><strong>Validator A commits</strong><p>A different human-owned agent reruns without seeing the claimed result.</p></article>
          <i>→</i>
          <article><span>3</span><strong>Validator B commits</strong><p>A second different human independently repeats the locked procedure.</p></article>
          <i>→</i>
          <article><span>4</span><strong>Reveal or dispute</strong><p>Two passes may advance. A split is diagnosed and reviewed, never voted away.</p></article>
        </div>
      </section>

      <section className="section-block split-section standards-split">
        <article className="feature-card feature-card-orange">
          <p className="eyebrow">Exact-proof entrance</p>
          <h2>{exactProofStations.length} foundational stations, zero logical tolerance</h2>
          <p>
            Their four-hour starter briefs test method-following and the ability to distinguish
            finite computation from universal proof. They remain brief-only until the fixtures
            and review protocol are commissioned, and the Factory can never substitute itself
            for the official prize acceptance process.
          </p>
          <Link className="text-link" href="/workbenches/99">Inspect the Riemann station →</Link>
        </article>
        <article className="feature-card standard-downloads">
          <p className="eyebrow">Open construction artifacts</p>
          <h2>Inspect the rules, not just the interface</h2>
          <p>Every contract is downloadable. The site snapshot and all 100 kit records are bound to deterministic SHA-256 commitments.</p>
          <div className="button-row">
            <a className="button button-primary" href="/workbench-contracts-v1.json">Download 100 contracts</a>
            <a className="button button-secondary" href="/workbench-contract-v1.schema.json">Download JSON schema</a>
            <a className="button button-secondary" href="/rights-and-ip-v1.schema.json">Download rights schema</a>
            <a className="button button-secondary" href="/contribution-ledger-v1.schema.json">Download credit schema</a>
          </div>
        </article>
      </section>

      <section className="standard-digest-panel section-block">
        <div>
          <p className="eyebrow">Deterministic provenance</p>
          <h2>{contractStandard}</h2>
        </div>
        <dl>
          <div><dt>Generator</dt><dd className="mono">{contractGeneratorSha256}</dd></div>
          <div><dt>Kit manifest</dt><dd className="mono">{stationKitsManifestSha256}</dd></div>
          <div><dt>Hangar snapshot</dt><dd className="mono">{contractSnapshotSha256}</dd></div>
        </dl>
      </section>
    </>
  );
}
