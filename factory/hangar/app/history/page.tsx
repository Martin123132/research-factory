import type { Metadata } from "next";
import { HistoryExplorer } from "@/components/HistoryExplorer";

export const metadata: Metadata = {
  title: "Hangar history",
  description: "Search append-only activity and inspect current artifact standing without erasing history.",
};

export const dynamic = "force-dynamic";

export default function HistoryPage() {
  return (
    <>
      <section className="page-heading"><p className="eyebrow">Operational provenance / append only</p><h1>Hangar history</h1><p>Search what was built, blocked, reviewed, or commissioned. A correction changes current standing through a new hash-linked record; the original bytes and every intermediate conclusion stay visible.</p></section>
      <HistoryExplorer />
    </>
  );
}
