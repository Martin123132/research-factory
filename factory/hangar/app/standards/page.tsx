import type { Metadata } from "next";
import Link from "next/link";
import { ScopeNotice } from "@/components/ScopeNotice";
import appeal from "@/data/appeal-example.json";
import dispatchBudget from "@/data/dispatch-budget-example.json";
import supportDisclosure from "@/data/support-disclosure-example.json";
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
  ["08", "Bounded dispatch", "Every new runner must pass all 18 universal budget dimensions. Partial monitoring produces a rejection ticket; only the human can release a workload and the agent cannot enlarge its own authority."],
  ["09", "Conflict-independent appeals", "A named involved person cannot sit on the panel. Reviewers commit distinct evidence; a split returns to diagnosis, never a majority vote."],
  ["10", "Public material support", "Funding, credits, subsidies and decision conflicts are append-only public declarations. They cannot change evidence gates, measurement or promotion."],
  ["11", "Recoverable stewardship", "A disposable offline-release drill can recreate a clean local branch without credentials or a hosted remote. It cannot prove that two independent maintainers have actually completed the handover."],
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
            <p>WB-001 has frozen public inputs, a verifier, runner protocol, starter gate and a complete synthetic dispute drill. Its timing and identity boundaries are still not promotion-grade.</p>
          </article>
          <article className="stage-locked">
            <span className="stage-number mono">{String(contractCounts.live_ready).padStart(2, "0")}</span>
            <p className="eyebrow">Live ready</p>
            <h3>Locked by design</h3>
            <p>External identity, a central blind evaluator, promotion-grade isolated execution and explicit authorization must all exist before this count can move.</p>
          </article>
        </div>
      </section>

      <section className="section-block dispatch-gate-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Universal dispatch budget / verified synthetic projection</p>
            <h2>Partial enforcement means no process authority.</h2>
          </div>
          <p>
            The preflight checks time, compute, spend, tools, paths, network, hazards and stop
            authority before a runner can begin. A self-description cannot create enforcement.
          </p>
        </div>
        <div className="dispatch-gate-grid">
          <article className="dispatch-profile-card dispatch-profile-pass">
            <div className="card-topline"><span>ADMISSION PASS</span><span className="mono">DRY RUN ONLY</span></div>
            <h3>No-execution preflight</h3>
            <p className="mono">{dispatchBudget.dryRun.profileId}</p>
            <dl>
              <div><dt>Enforced</dt><dd>{dispatchBudget.dryRun.enforcedDimensions}/{dispatchBudget.dryRun.requiredDimensions}</dd></div>
              <div><dt>Scope</dt><dd>{dispatchBudget.dryRun.authorizationScope.replaceAll("_", " ")}</dd></div>
              <div><dt>Process started</dt><dd>{dispatchBudget.processStarted ? "YES" : "NO"}</dd></div>
            </dl>
            <p>Zero time, compute, storage, spend, tools, file access and network access are granted.</p>
          </article>
          <article className="dispatch-profile-card dispatch-profile-reject">
            <div className="card-topline"><span>ADMISSION REJECTED</span><span className="mono">PROCESS EXECUTION</span></div>
            <h3>Frozen local monitored runner</h3>
            <p className="mono">{dispatchBudget.process.profileId}</p>
            <dl>
              <div><dt>Enforced</dt><dd>{dispatchBudget.process.enforcedDimensions}/{dispatchBudget.process.requiredDimensions}</dd></div>
              <div><dt>Missing</dt><dd>{dispatchBudget.process.missingDimensions.length}</dd></div>
              <div><dt>Authority</dt><dd>{dispatchBudget.process.authorizationScope}</dd></div>
            </dl>
            <ul className="dispatch-missing-list">
              {dispatchBudget.process.missingDimensions.map((dimension) => (
                <li key={dimension}>{dimension.replaceAll("_", " ")}</li>
              ))}
            </ul>
          </article>
        </div>
        <div className="dispatch-gate-boundary">
          <strong>NO PROCESS EXECUTION / NO SCIENTIFIC STANDING</strong>
          <span className="mono">report sha256:{dispatchBudget.reportSha256}</span>
          <p>Human release is still required. This static panel is not the engine gate or an execution ticket.</p>
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

      <section className="section-block split-section standards-split">
        <article className="feature-card feature-card-orange">
          <p className="eyebrow">Procedural appeals / verified synthetic projection</p>
          <h2>Interested people cannot review their own dispute.</h2>
          <p>
            The appeal ledger structurally excludes the requester and every named materially
            involved author, validator or reviewer. Every panel member declares no material
            conflict and commits a separate evidence hash.
          </p>
          <dl className="dispatch-card-dl">
            <div><dt>Conflicted reviewer</dt><dd>{appeal.conflictedReviewerRejected ? "REJECTED" : "NOT TESTED"}</dd></div>
            <div><dt>Panel commitments</dt><dd>{appeal.reviewerCount}</dd></div>
            <div><dt>Split outcome</dt><dd>{appeal.outcome.replaceAll("_", " ")}</dd></div>
          </dl>
        </article>
        <article className="feature-card">
          <p className="eyebrow">No appeal court for scientific truth</p>
          <h2>Consensus, or back to diagnosis.</h2>
          <p>
            A split cannot be voted away. It returns to a fresh diagnostic run. Even a unanimous
            procedural uphold only asks for a separate correction or remedy record; it cannot
            change scientific standing automatically.
          </p>
          <p className="mono">appeal record sha256:{appeal.recordSha256}</p>
          <p>Identity records still do not prove that a named account is a distinct human.</p>
        </article>
      </section>

      <section className="section-block split-section standards-split">
        <article className="feature-card feature-card-orange">
          <p className="eyebrow">Material support / verified synthetic projection</p>
          <h2>Material support cannot buy a pass.</h2>
          <p>
            Funding, compute credits, provider subsidies and decision conflicts are public,
            append-only declarations at the affected scope. The ledger is for a factual public
            description, never private agreements or a ranking of contributors.
          </p>
          <dl className="dispatch-card-dl">
            <div><dt>Lifecycle records</dt><dd>{supportDisclosure.records}</dd></div>
            <div><dt>Disclosure ended</dt><dd>{supportDisclosure.endedDisclosure ? "YES" : "NO"}</dd></div>
            <div><dt>Truth gates changed</dt><dd>{supportDisclosure.boundary.scientificGatesChanged ? "YES" : "NO"}</dd></div>
          </dl>
        </article>
        <article className="feature-card">
          <p className="eyebrow">Non-influence boundary</p>
          <h2>Declare it. Do not use it as evidence.</h2>
          <p>
            A support record cannot alter measurement, promotion or a validator requirement. It
            also cannot prove that a person is independent, authorised or legally cleared.
          </p>
          <p className="mono">report sha256:{supportDisclosure.reportSha256}</p>
          <p>{supportDisclosure.scientificStanding.replaceAll("_", " ")} / promotion: {supportDisclosure.eligibleForPromotion ? "ELIGIBLE" : "INELIGIBLE"}</p>
        </article>
      </section>

      <section className="section-block split-section standards-split">
        <article className="feature-card feature-card-orange">
          <p className="eyebrow">Key-person recovery / technical drill</p>
          <h2>The project must survive its own founder.</h2>
          <p>
            A maintainer can verify an offline release, recover its history into a clean local
            branch, remove the bundle origin and check Git object integrity without credentials
            or upstream write authority.
          </p>
        </article>
        <article className="feature-card">
          <p className="eyebrow">Observed-human boundary</p>
          <h2>Software cannot invent a second person.</h2>
          <p>
            The drill records that its operator identity and independence are unproven. A real,
            reviewable two-maintainer handover is still required before the resilience control can
            move from blocked to observed.
          </p>
          <a className="text-link" href="https://github.com/Martin123132/research-factory/tree/main/factory/recovery">Inspect the recovery drill &rarr;</a>
        </article>
      </section>

      <section className="section-block standard-flow-section">
        <div className="section-heading">
          <div><p className="eyebrow">Work Order Envelope v2</p><h2>The worker knows the fence before the clock starts</h2></div>
        </div>
        <div className="standard-flow" aria-label="Bounded work dispatch flow">
          <article><span>1</span><strong>Claim one unit</strong><p>The named operator receives one expiring, exclusive work claim.</p></article>
          <i>â†’</i>
          <article><span>2</span><strong>Administrator issues</strong><p>Exact command, interfaces, time, output, zero local cost and stop conditions are hash-bound.</p></article>
          <i>â†’</i>
          <article><span>3</span><strong>Human releases</strong><p>The agent cannot start without the separately retained release capability.</p></article>
          <i>â†’</i>
          <article><span>4</span><strong>Receipt decides route</strong><p>In-envelope work may submit. Stopped or over-limit work is retained but cannot enter reruns.</p></article>
        </div>
        <div className="scope-notice scope-notice-compact">
          <strong>Commissioning boundary</strong>
          <p>
            <span className="mono">LOCAL_MONITORED_V1</span> enforces argv, working directory,
            wall time and output size. It does not prove network, filesystem, memory or human
            identity isolation, so every receipt remains explicitly ineligible for promotion.
          </p>
        </div>
      </section>

      <section className="section-block split-section standards-split">
        <article className="feature-card feature-card-orange">
          <p className="eyebrow">Commissioning drill / zero scientific credit</p>
          <h2>The disagreement route is executable</h2>
          <p>
            A disposable WB-001 shift now runs the bounded author attempt, two blind reruns,
            a deliberate split, one diagnostic rerun, dispute escalation and a public-ledger
            blindness audit. The diagnostic majority remains blocked from promotion.
          </p>
          <a className="text-link" href="https://github.com/Martin123132/research-factory/tree/main/factory/commissioning">
            Inspect and run the drill &rarr;
          </a>
        </article>
        <article className="feature-card">
          <p className="eyebrow">Identity boundary</p>
          <h2>Records are not people</h2>
          <p>
            The local drill uses five distinct synthetic provider/subject records so the state
            machine can be tested. Its schema permanently records that distinct humans are not
            proven and that every output carries zero promotion credit.
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
            <a className="button button-secondary" href="/shift-report-v1.schema.json">Download shift-report schema</a>
            <a className="button button-secondary" href="https://github.com/Martin123132/research-factory/tree/main/factory/control_plane/schemas">Inspect envelope schemas</a>
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
