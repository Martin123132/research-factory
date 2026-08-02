import type { Metadata } from "next";
import { OperationsBoard } from "@/components/OperationsBoard";
import { workbenchCode, workbenches } from "@/lib/workbenches";

export const metadata: Metadata = {
  title: "Shift board",
  description: "Schedule hangar construction and synthetic commissioning work.",
};

export const dynamic = "force-dynamic";

export default async function OperationsPage({
  searchParams,
}: {
  searchParams: Promise<{ workbench?: string }>;
}) {
  const requested = Number((await searchParams).workbench);
  const initialWorkbenchId =
    Number.isInteger(requested) && requested >= 1 && requested <= 100 ? requested : 1;
  const stations = workbenches.map((workbench) => ({
    id: workbench.id,
    code: workbenchCode(workbench.id),
    title: workbench.workbench,
  }));
  return (
    <>
      <section className="page-heading page-heading-row">
        <div><p className="eyebrow">Operations / non-scientific</p><h1>The shift board</h1><p>Schedule the work that builds and tests the factory itself. Commands are revision-checked; state changes append to the permanent hangar log.</p></div>
        <div className="page-status-card"><span>LIVE RESEARCH</span><strong>LOCKED</strong><small>0 claimable units exposed here</small></div>
      </section>
      <OperationsBoard stations={stations} initialWorkbenchId={initialWorkbenchId} />
    </>
  );
}
