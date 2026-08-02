import type { Metadata } from "next";
import Link from "next/link";
import { listActivity, listRunners, listWorkOrders } from "@/db/repository";
import type { ActivityEvent, RunnerProfile, WorkOrder } from "@/lib/factory-types";
import {
  categoryCounts,
  getWorkbench,
  workbenchCode,
  workbenches,
} from "@/lib/workbenches";

export const metadata: Metadata = {
  title: "Hangar overview",
  description:
    "Construction status for the Research Factory's 100 workbench stations.",
};

export const dynamic = "force-dynamic";

async function operationalSnapshot(): Promise<{
  orders: WorkOrder[];
  runners: RunnerProfile[];
  activity: ActivityEvent[];
  databaseReady: boolean;
}> {
  try {
    const [orders, runners, activity] = await Promise.all([
      listWorkOrders(20),
      listRunners(),
      listActivity({ limit: 5 }),
    ]);
    return { orders, runners, activity, databaseReady: true };
  } catch {
    return { orders: [], runners: [], activity: [], databaseReady: false };
  }
}

export default async function Home() {
  const snapshot = await operationalSnapshot();
  const instrumented = workbenches.filter((item) => item.implementation_status).length;
  const activeOrders = snapshot.orders.filter((order) => order.status !== "COMPLETED");
  const testArticle = getWorkbench(1)!;

  return (
    <>
      <section className="hero panel-grid">
        <div className="hero-copy">
          <p className="eyebrow">Hangar construction / phase 01</p>
          <h1>One hundred stations. One evidence standard.</h1>
          <p className="hero-lede">
            Build the workshop before asking it for breakthroughs. This workspace maps every
            station, schedules construction, commissions the plumbing, and keeps those drills
            structurally separate from science.
          </p>
          <div className="button-row">
            <Link className="button button-primary" href="/workbenches">
              Enter the station floor
            </Link>
            <Link className="button button-secondary" href="/operations">
              Open shift board
            </Link>
          </div>
        </div>
        <div className="hero-instrument" aria-label="Factory readiness summary">
          <div className="instrument-heading">
            <span>Hangar readiness</span>
            <span className="mono">RF-H01</span>
          </div>
          <div className="readiness-dial">
            <span className="readiness-value">100</span>
            <span className="readiness-label">catalogued stations</span>
          </div>
          <div className="instrument-bars">
            <div><span>Registry</span><i style={{ width: "100%" }} /></div>
            <div><span>Instrumented</span><i style={{ width: "1%" }} /></div>
            <div><span>Live research</span><i className="bar-zero" style={{ width: "0%" }} /></div>
          </div>
          <p className="instrument-note">
            A zero in the live lane is the correct reading for this phase.
          </p>
        </div>
      </section>

      <section className="stat-grid" aria-label="Hangar statistics">
        <article className="stat-card"><strong>100</strong><span>objective workbench briefs</span></article>
        <article className="stat-card"><strong>9</strong><span>physical and computational domains</span></article>
        <article className="stat-card"><strong>{instrumented}</strong><span>instrumented test article</span></article>
        <article className="stat-card stat-card-safe"><strong>0</strong><span>live investigations claimed</span></article>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><p className="eyebrow">Station map</p><h2>The factory floor</h2></div>
          <Link className="text-link" href="/workbenches">Browse all 100 →</Link>
        </div>
        <div className="category-grid">
          {categoryCounts.map((item, index) => (
            <Link
              className="category-card"
              href={`/workbenches?category=${encodeURIComponent(item.category)}`}
              key={item.category}
            >
              <span className="category-index mono">{String(index + 1).padStart(2, "0")}</span>
              <strong>{item.category}</strong>
              <span>{item.count} stations</span>
              <div className="category-meter"><i style={{ width: `${(item.count / 14) * 100}%` }} /></div>
            </Link>
          ))}
        </div>
      </section>

      <section className="split-section section-block">
        <article className="feature-card feature-card-orange">
          <div className="card-topline">
            <span className="status-dot" />
            <span>Instrumented test article</span>
            <span className="mono">{workbenchCode(testArticle.id)}</span>
          </div>
          <h2>{testArticle.workbench}</h2>
          <p>
            The single station currently fitted with a contract, runner, isolation prototype,
            and commissioning history. It remains unclaimed for live research.
          </p>
          <Link className="text-link" href="/workbenches/1">Inspect the station →</Link>
        </article>

        <article className="feature-card">
          <div className="card-topline">
            <span className={snapshot.databaseReady ? "status-dot status-dot-green" : "status-dot status-dot-amber"} />
            <span>Operational layer</span>
            <span className="mono">D1 / isolated</span>
          </div>
          <h2>{activeOrders.length} active orders · {snapshot.runners.length} runners</h2>
          <p>
            {snapshot.databaseReady
              ? "The shift board is online. Every mutation is attributed and written to the append-only hangar activity stream."
              : "The dashboard can read the catalogue; operational storage will come online when its D1 binding starts."}
          </p>
          <Link className="text-link" href="/operations">Open operations →</Link>
        </article>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><p className="eyebrow">Control boundary</p><h2>What this hangar can—and cannot—do</h2></div>
        </div>
        <div className="guardrail-grid">
          <article><span>01</span><h3>Construct</h3><p>Turn a brief into a frozen contract, benchmark, runner, and review plan.</p></article>
          <article><span>02</span><h3>Commission</h3><p>Exercise workflows with visibly synthetic jobs and known fixtures.</p></article>
          <article><span>03</span><h3>Retain</h3><p>Keep searchable operational failures so the same plumbing mistake is not repeated.</p></article>
          <article className="guardrail-stop"><span>LOCKED</span><h3>No scientific promotion</h3><p>Nothing here counts as evidence, independent reproduction, a holdout pass, or a result.</p></article>
        </div>
      </section>

      {snapshot.activity.length > 0 && (
        <section className="section-block">
          <div className="section-heading">
            <div><p className="eyebrow">Recent log</p><h2>Latest hangar activity</h2></div>
            <Link className="text-link" href="/history">Search history →</Link>
          </div>
          <div className="activity-mini-list">
            {snapshot.activity.map((event) => (
              <div key={event.eventId}>
                <span className="mono">#{event.sequence}</span>
                <strong>{event.summary}</strong>
                <time>{new Date(event.createdAt).toLocaleString("en-GB")}</time>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
