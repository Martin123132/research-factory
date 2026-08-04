import type { Metadata } from "next";
import Link from "next/link";
import { ScopeNotice } from "@/components/ScopeNotice";

export const metadata: Metadata = {
  title: "System boundary",
  description: "The Research Factory Hangar architecture and scientific boundary.",
};

export default function ArchitecturePage() {
  return (
    <>
      <section className="page-heading page-heading-row">
        <div><p className="eyebrow">System / trust architecture</p><h1>The hangar is not the laboratory</h1><p>It constructs standard work areas and rehearses their governance. The scientific control plane remains a separate trust domain with separate identity counts, evidence, holdouts, and promotion authority.</p></div>
        <div className="page-status-card"><span>BOUNDARY</span><strong>ONE-WAY</strong><small>Future handoff is proposal-only</small></div>
      </section>
      <ScopeNotice />
      <section className="system-flow" aria-label="Research Factory system flow">
        <article><span className="flow-index">01</span><p className="eyebrow">Catalogue</p><h2>100 external truth conditions</h2><p>Versioned, source-backed station briefs. Read-only inside the hangar.</p></article>
        <i>→</i>
        <article><span className="flow-index">02</span><p className="eyebrow">Construction</p><h2>Contracts and tooling</h2><p>Human-attributed work orders turn briefs into runnable infrastructure.</p></article>
        <i>→</i>
        <article className="flow-synthetic"><span className="flow-index">03</span><p className="eyebrow">Synthetic commissioning</p><h2>Factory plumbing drills</h2><p>Known fixtures exercise states, identity surfaces, and review routing.</p></article>
        <i className="flow-lock">‖</i>
        <article className="flow-locked"><span className="flow-index">04</span><p className="eyebrow">Separate control plane</p><h2>Live science</h2><p>Starts at zero identities, zero reproductions, and zero evidence after independent authorization.</p></article>
      </section>
      <section className="section-block">
        <div className="section-heading"><div><p className="eyebrow">Enforced interfaces</p><h2>Four boundaries that keep the record honest</h2></div></div>
        <div className="architecture-grid">
          <article><span className="architecture-tag">IDENTITY</span><h3>Server-derived operators</h3><p>Writes use the platform user ID injected by the private workspace. Email and display name are labels, never authority keys.</p></article>
          <article><span className="architecture-tag">STATE</span><h3>Commands, not arbitrary status</h3><p>Claim, start, block, review, and close are explicit commands checked against the current revision.</p></article>
          <article><span className="architecture-tag">RUNNERS</span><h3>Non-promotion trust classes</h3><p>Hangar 01 accepts trusted local code or container commissioning prototypes. It has no execute or upload endpoint.</p></article>
          <article><span className="architecture-tag">HISTORY</span><h3>Append-only operational memory</h3><p>The database rejects event and shift-report updates or deletes. Reports hash-link progress, no-gain, blocked and unrunnable work without changing the parent order.</p></article>
        </div>
      </section>
      <section className="handoff-panel">
        <div><p className="eyebrow">Future interface / not yet enabled</p><h2>Construction can propose a handoff. It cannot create a live round.</h2><p>A future bundle may carry contracts, tool hashes, and commissioning history as design provenance. A separate control-plane administrator must review it, freeze a new round, and start every scientific count at zero.</p></div>
        <Link className="button button-secondary" href="/history">Inspect hangar provenance</Link>
      </section>
    </>
  );
}
