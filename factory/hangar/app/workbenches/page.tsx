import type { Metadata } from "next";
import { WorkbenchDirectory } from "@/components/WorkbenchDirectory";
import { workbenches } from "@/lib/workbenches";

export const metadata: Metadata = {
  title: "Station floor",
  description: "Browse all 100 objective Research Factory workbench briefs.",
};

export default async function WorkbenchesPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string }>;
}) {
  const { category } = await searchParams;
  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Station floor / catalogue v1</p>
        <h1>One hundred bounded problems</h1>
        <p>
          Each station starts with an external truth condition, a reference benchmark, a hard
          gate, and an economic or physical guardrail. A brief becomes runnable only after its
          construction work is finished.
        </p>
      </section>
      <WorkbenchDirectory items={workbenches} initialCategory={category} />
    </>
  );
}
