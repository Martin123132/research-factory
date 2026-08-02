import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ScopeNotice } from "@/components/ScopeNotice";
import {
  getWorkbench,
  referenceLinks,
  workbenchCode,
  workbenchReadiness,
} from "@/lib/workbenches";

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
  const references = referenceLinks(workbench.reference_url);

  return (
    <>
      <div className="breadcrumb">
        <Link href="/workbenches">Station floor</Link><span>/</span><strong>{workbenchCode(workbench.id)}</strong>
      </div>
      <section className="station-hero">
        <div>
          <div className="card-topline">
            <span className={workbench.implementation_status ? "status-dot status-dot-green" : "status-dot"} />
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
              <div><dt>Contract</dt><dd>{workbench.contract_version ?? "Not built"}</dd></div>
              <div><dt>Live work</dt><dd>Locked</dd></div>
            </dl>
            <Link className="button button-primary button-full" href={`/operations?workbench=${workbench.id}`}>
              Create build order
            </Link>
          </div>
        </aside>
      </section>
    </>
  );
}
