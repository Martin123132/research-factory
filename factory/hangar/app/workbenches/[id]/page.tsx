import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ScopeNotice } from "@/components/ScopeNotice";
import {
  getWorkbench,
  referenceLinks,
  workbenchCode,
  workbenchReadiness,
  workbenchStatusDot,
} from "@/lib/workbenches";
import { getWorkbenchContract } from "@/lib/workbench-contracts";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const workbench = getWorkbench(Number(id));
  return {
    title: workbench
      ? `${workbenchCode(workbench.id)} — ${workbench.workbench}`
      : "Station not found",
  };
}

export default async function WorkbenchPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const workbench = getWorkbench(Number(id));
  if (!workbench) notFound();
  const contract = getWorkbenchContract(workbench.id);
  if (!contract) notFound();
  const references = referenceLinks(workbench.reference_url);

  return (
    <>
      <div className="breadcrumb">
        <Link href="/workbenches">Station floor</Link><span>/</span><strong>{workbenchCode(workbench.id)}</strong>
      </div>
      <section className="station-hero">
        <div>
          <div className="card-topline">
            <span className={workbenchStatusDot(workbench)} />
            <span>{workbenchReadiness(workbench)}</span>
            <span className="mono">CATALOGUE V1</span>
          </div>
          <p className="eyebrow">{workbench.short_category} / {workbench.evidence_lane}</p>
          <h1>{workbench.workbench}</h1>
          <p className="station-track">{workbench.track}</p>
        </div>
        <div className="station-number mono">{workbenchCode(workbench.id)}</div>
      </section>
      <ScopeNotice compact={workbench.id !== 1} />
      <section className="station-layout">
        <div className="station-main">
          <article className="spec-block"><span className="spec-number">01</span><div><p className="eyebrow">Hard gate and score</p><h2>What has to be true</h2><p>{workbench.hard_gate_and_score}</p></div></article>
          <article className="spec-block"><span className="spec-number">02</span><div><p className="eyebrow">Economic / physical guardrail</p><h2>What makes it useful</h2><p>{workbench.economic_or_physical_guardrail}</p></div></article>
          <article className="spec-block"><span className="spec-number">03</span><div><p className="eyebrow">Entry pack</p><h2>Proof of care before submission</h2><p>{workbench.starter_pack}</p></div></article>
          <article className="spec-block contract-gates">
            <span className="spec-number">04</span>
            <div>
              <p className="eyebrow">Workbench Contract v1</p>
              <h2>{contract.unresolved_count} gates remain before live work</h2>
              <p>
                {contract.commissioning_profile === "ADAPTER_BOUND"
                  ? "A reusable commissioning adapter has fitted the measurable pieces that genuinely exist. Missing official inputs, scorers, resource controls or authority remain visible; adapter-bound does not mean commissioned."
                  : "The contract separates a useful brief from a commissioned station. Missing verifiers, fixtures, runners or identity controls remain visible; the generator is not allowed to invent them."}
              </p>
              <ul className="gate-list">
                {contract.unresolved.slice(0, 8).map((gate) => <li key={gate}>{gate.replaceAll("_", " ")}</li>)}
              </ul>
              {contract.unresolved.length > 8 && (
                <p className="gate-more">+ {contract.unresolved.length - 8} further commissioning gates</p>
              )}
            </div>
          </article>
        </div>
        <aside className="station-sidebar">
          <div className="sidebar-panel">
            <p className="eyebrow">Reference benchmark</p>
            <h3>{workbench.benchmark}</h3>
            {references.map((href, index) => (
              <a className="text-link" href={href} target="_blank" rel="noreferrer" key={href}>
                Open source {references.length > 1 ? index + 1 : ""} ↗
              </a>
            ))}
          </div>
          <div className="sidebar-panel">
            <p className="eyebrow">Construction state</p>
            <dl>
              <div><dt>Readiness</dt><dd>{workbenchReadiness(workbench)}</dd></div>
              <div><dt>Contract</dt><dd>v{contract.contract_version}</dd></div>
              <div><dt>Profile</dt><dd>{contract.commissioning_profile.replaceAll("_", " ")}</dd></div>
              {contract.adapter_id && <div><dt>Adapter</dt><dd>{contract.adapter_id.replaceAll("_", " ")} v{contract.adapter_version}</dd></div>}
              <div><dt>Starter</dt><dd>{contract.starter_pack_status.replaceAll("_", " ")}</dd></div>
              <div><dt>Digest</dt><dd className="mono">{contract.contract_sha256.slice(0, 12)}…</dd></div>
              <div><dt>Live work</dt><dd>Locked</dd></div>
            </dl>
            <Link className="button button-primary button-full" href={`/operations?workbench=${workbench.id}`}>
              Create build order
            </Link>
            <Link className="button button-secondary button-full" href="/standards">
              Read the evidence standard
            </Link>
          </div>
          <div className="sidebar-panel">
            <p className="eyebrow">Open construction artifacts</p>
            <a className="text-link" href="/workbench-contracts-v1.json">All 100 contracts ↗</a>
            <a className="text-link" href="/workbench-contract-v1.schema.json">Contract schema ↗</a>
          </div>
        </aside>
      </section>
    </>
  );
}
