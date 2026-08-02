import type { Metadata } from "next";
import { RunnerRegistry } from "@/components/RunnerRegistry";
import { ScopeNotice } from "@/components/ScopeNotice";

export const metadata: Metadata = {
  title: "Runner interfaces",
  description: "Register non-promotion runner interfaces for factory commissioning.",
};

export const dynamic = "force-dynamic";

export default function RunnersPage() {
  return (
    <>
      <section className="page-heading page-heading-row">
        <div><p className="eyebrow">Infrastructure / runner boundary</p><h1>Runner interfaces</h1><p>Register what a machine is allowed to execute and the trust assumptions around it. This registry stores no credentials, uploads no code, and dispatches no research jobs.</p></div>
        <div className="page-status-card"><span>PROMOTION GRADE</span><strong>UNAVAILABLE</strong><small>All registered runners remain non-promotion</small></div>
      </section>
      <ScopeNotice compact />
      <RunnerRegistry />
    </>
  );
}
