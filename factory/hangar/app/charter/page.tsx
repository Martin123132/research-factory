import type { Metadata } from "next";
import quality from "@/data/factory-quality-summary.json";
import { ScopeNotice } from "@/components/ScopeNotice";

export const metadata: Metadata = {
  title: "Open Factory Charter",
  description:
    "Worker rights and a machine-verifiable, non-compensating quality profile for the Research Factory.",
};

const workerRights = [
  ["Open entrance", "Evidence and safety gates apply without a credential, employer, affiliation or payment requirement."],
  ["Bounded work", "Scope, duration, resources, hazards, stop conditions and evidence class must be known before dispatch."],
  ["Human authority", "A named person controls each agent's interfaces, budget and termination. The agent cannot expand itself."],
  ["Pause without penalty", "People may decline, pause or leave without losing earned attribution or being punished in scoring or access."],
  ["Your work stays yours", "The Factory records lawful rights and role-specific credit; it does not take contributor ownership."],
  ["Provider choice", "Compatible commercial, local and future tools may be used. No preferred model can alter the evidence gate."],
  ["Private means private", "Identity evidence, hidden answers, credentials, personal data and sensitive reports stay outside public Git."],
  ["Challenge without retaliation", "Technical and governance decisions can be disputed; an interested party cannot solely judge its own appeal."],
] as const;

const domainCopy: Record<string, string> = {
  ACCESS: "The core path is free and credential-neutral. Broader accommodation and non-web accessibility work remains open.",
  WORK: "Pause, exit and anti-volume protections are adopted. The universal budget gate exists, but no process runner yet enforces all 18 dimensions.",
  SCIENCE: "Contracts, blind states and independence rules are enforced synthetically. There are no live validators or live claims.",
  MEMORY: "Negative and shift memory is append-only and searchable. Universal corrections and retractions are closed, hash-linked and synthetically enforced.",
  RIGHTS: "Ownership, roles and commercial neutrality are separated. Conflict-excluded procedural appeals are append-only, tested and unable to alter scientific standing automatically.",
  RESILIENCE: "The engine, packages and recovery route are portable. A technical handover drill exists, but key-person recovery by another maintainer has not been observed.",
  GOVERNANCE: "Controls, evidence hashes and material-support disclosures verify in CI. No external audit has occurred.",
};

const certificationSteps = [
  ["Foundation only", "Current", "Construction mechanisms and honest gaps are public. This is a status, not a certification."],
  ["Operationally conformant", "Locked", "All 28 controls must meet their minimum and required mechanisms must have observed evidence."],
  ["Scientifically demonstrated", "Locked", "At least one live blind claim must complete two genuinely independent human reproductions."],
  ["Independently audited", "Locked", "A conflict-free external reviewer must verify the full evidence-bound profile."],
] as const;

function domainState(domain: (typeof quality.domains)[number]) {
  if (domain.blocked > 0) return "blocked";
  if (domain.partial > 0) return "partial";
  return "meets";
}

export default function CharterPage() {
  const certificationsActive = Object.values(quality.certifications).filter(Boolean).length;

  return (
    <>
      <section className="page-heading-row charter-heading">
        <div className="page-heading">
          <p className="eyebrow">Open Factory Charter / quality standard v{quality.standard_version}</p>
          <h1>A better factory is measurable.</h1>
          <p>
            Quality here means fair working conditions, blind evidence, useful memory,
            contributor rights and infrastructure that survives its founder. Strong performance
            in one domain cannot buy forgiveness in another.
          </p>
        </div>
        <div className="page-status-card charter-readout">
          <span className="mono">CURRENT PROFILE</span>
          <strong>Foundation only</strong>
          <p>honest construction status — not certified</p>
          <dl>
            <div><dt>Meets</dt><dd>{quality.summary.meets}</dd></div>
            <div><dt>Partial</dt><dd>{quality.summary.partial}</dd></div>
            <div><dt>Blocked</dt><dd>{quality.summary.blocked}</dd></div>
            <div><dt>Certifications</dt><dd>{certificationsActive}</dd></div>
          </dl>
        </div>
      </section>

      <ScopeNotice compact />

      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Worker bill of rights</p>
            <h2>People do not become fuel for the loop</h2>
          </div>
          <p>
            A failed gate rejects evidence, not a person&apos;s intelligence or worth. Honest stopping
            and useful failure are part of the job.
          </p>
        </div>
        <div className="charter-rights-grid">
          {workerRights.map(([title, body], index) => (
            <article key={title}>
              <span className="mono">{String(index + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block quality-profile-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Seven non-compensating domains</p>
            <h2>No overall score to game</h2>
          </div>
          <p>
            Open code cannot cancel stolen credit. Fast runners cannot cancel unsafe work. A
            breakthrough cannot cancel answer leakage.
          </p>
        </div>
        <div className="quality-domain-grid">
          {quality.domains.map((domain) => (
            <article className={`quality-domain quality-domain-${domainState(domain)}`} key={domain.domain_id}>
              <div className="quality-domain-topline">
                <span className="mono">{domain.domain_id}</span>
                <strong>{domainState(domain)}</strong>
              </div>
              <h3>{domain.title}</h3>
              <p>{domainCopy[domain.domain_id]}</p>
              <dl>
                <div><dt>Meets</dt><dd>{domain.meets}</dd></div>
                <div><dt>Partial</dt><dd>{domain.partial}</dd></div>
                <div><dt>Blocked</dt><dd>{domain.blocked}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block charter-ladder-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Certification ladder</p>
            <h2>Claims unlock only when evidence exists</h2>
          </div>
        </div>
        <div className="charter-ladder">
          {certificationSteps.map(([title, state, body], index) => (
            <article className={state === "Current" ? "ladder-current" : "ladder-locked"} key={title}>
              <div><span className="mono">Q{index}</span><strong>{state}</strong></div>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block charter-gap-panel">
        <div>
          <p className="eyebrow">Why certification remains zero</p>
          <h2>The Factory publishes the missing machinery.</h2>
          <p>
            It still needs a process runner that passes the universal dispatch budget,
            recovery by another maintainer, two independent validators, a live two-person reproduction and an external
            quality audit.
          </p>
        </div>
        <dl>
          <div><dt>Live stations</dt><dd>{quality.operating_facts.live_research_stations}</dd></div>
          <div><dt>Independent validators</dt><dd>{quality.operating_facts.independent_human_validators_onboarded}</dd></div>
          <div><dt>Observed live reproductions</dt><dd>{quality.operating_facts.observed_live_two_person_reproductions}</dd></div>
          <div><dt>Independent audits</dt><dd>{quality.operating_facts.independent_quality_audits}</dd></div>
        </dl>
      </section>

      <section className="section-block charter-artifacts">
        <div>
          <p className="eyebrow">Inspect the exact rules</p>
          <h2>Do not trust this page.</h2>
          <p>
            Run the verifier. It checks the closed 28-control standard, every cited evidence hash,
            derived counts, station readiness and certification prerequisites.
          </p>
        </div>
        <div className="button-row">
          <a className="button button-primary" href="https://github.com/Martin123132/research-factory/blob/main/OPEN_FACTORY_CHARTER.md">Read the Charter</a>
          <a className="button button-secondary" href="https://github.com/Martin123132/research-factory/blob/main/FACTORY_QUALITY_STANDARD.md">Read the standard</a>
          <a className="button button-secondary" href="https://raw.githubusercontent.com/Martin123132/research-factory/main/factory/quality/factory-quality-standard-v1.json">Download 28 controls</a>
          <a className="button button-secondary" href="https://raw.githubusercontent.com/Martin123132/research-factory/main/factory/quality/current-assessment.json">Download assessment</a>
        </div>
      </section>
    </>
  );
}
