import type { Metadata } from "next";
import { HistoryExplorer } from "@/components/HistoryExplorer";

export const metadata: Metadata = {
  title: "Hangar history",
  description: "Search append-only construction and synthetic commissioning activity.",
};

export const dynamic = "force-dynamic";

export default function HistoryPage() {
  return (
    <>
      <section className="page-heading"><p className="eyebrow">Operational provenance / append only</p><h1>Hangar history</h1><p>Search what was built, blocked, reviewed, or commissioned. Corrections create a new event; prior failures are never polished out of the record.</p></section>
      <HistoryExplorer />
    </>
  );
}
