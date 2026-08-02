import type { Metadata } from "next";
import Link from "next/link";
import { ScopeNotice } from "@/components/ScopeNotice";

export const metadata: Metadata = {
  title: "Workflow tutorial",
  description:
    "A guided synthetic walkthrough of the Research Factory Hangar workflow and its evidence boundary.",
};

const chapters = [
  { time: "00:00", title: "The question", text: "Why producing an answer is different from earning trust." },
  { time: "00:10", title: "Choose a bounded problem", text: "Start with an external truth condition and measurable gates." },
  { time: "00:28", title: "Read the contract", text: "Inspect the benchmark, hard pass condition, and physical guardrails." },
  { time: "00:49", title: "Control the work", text: "Create an attributed order and use revision-checked state commands." },
  { time: "01:12", title: "Declare the runner", text: "Record what a machine may execute and what it cannot claim." },
  { time: "01:29", title: "Preserve attempts", text: "Keep failures and corrections searchable in append-only history." },
  { time: "01:45", title: "Keep science separate", text: "Stop synthetic commissioning at the scientific bulkhead." },
  { time: "02:16", title: "The workflow", text: "Bound, gate, attribute, constrain, retain, and separate." },
];

export default function TutorialPage() {
  return (
    <>
      <section className="page-heading page-heading-row tutorial-heading">
        <div>
          <p className="eyebrow">Orientation / synthetic walkthrough</p>
          <h1>See the whole workflow in two and a half minutes.</h1>
          <p>
            Follow one test article from the station floor to the scientific boundary.
            The callouts explain not only what each control does, but why it exists.
          </p>
        </div>
        <div className="page-status-card tutorial-duration-card">
          <span>GUIDED TOUR</span>
          <strong>02:35</strong>
          <small>8 chapters · English captions</small>
        </div>
      </section>

      <ScopeNotice />

      <section className="tutorial-stage" aria-labelledby="tutorial-video-title">
        <div className="tutorial-stage-topline">
          <div>
            <span className="status-dot status-dot-green" />
            <span id="tutorial-video-title">Research Factory Hangar workflow</span>
          </div>
          <span className="mono">SYNTHETIC DEMONSTRATION / RF-T01</span>
        </div>
        <div className="tutorial-screen">
          <video
            controls
            playsInline
            preload="metadata"
            poster="/tutorial-poster.jpg"
            aria-describedby="tutorial-video-boundary"
          >
            <source src="/research-factory-hangar-workflow.mp4" type="video/mp4" />
            <track
              default
              kind="captions"
              label="English"
              src="/research-factory-hangar-workflow.vtt"
              srcLang="en"
            />
            Your browser does not support embedded video. The full transcript is available below.
          </video>
        </div>
        <div className="tutorial-stage-boundary" id="tutorial-video-boundary">
          <span>Training standing</span>
          <strong>NO SCIENTIFIC CREDIT</strong>
          <p>This walkthrough demonstrates controls; it submits no work, evidence, reproduction, or result.</p>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading">
          <div><p className="eyebrow">Chapter map</p><h2>What the tour explains</h2></div>
        </div>
        <div className="tutorial-chapter-grid">
          {chapters.map((chapter, index) => (
            <article key={chapter.time}>
              <div><span className="mono">{String(index + 1).padStart(2, "0")}</span><time>{chapter.time}</time></div>
              <h3>{chapter.title}</h3>
              <p>{chapter.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="tutorial-after section-block">
        <div>
          <p className="eyebrow">After the tour</p>
          <h2>Walk the same route yourself.</h2>
          <p>
            Browse the measurable problem contracts first. Open WB-001 to see the instrumented
            test article, then inspect the synthetic order and its permanent event trail.
          </p>
        </div>
        <div className="tutorial-actions">
          <Link className="button button-primary" href="/workbenches/1">Open WB-001</Link>
          <Link className="button tutorial-dark-button" href="/operations?workbench=1">Open the shift board</Link>
          <Link className="text-link" href="/history">Inspect append-only history →</Link>
        </div>
      </section>

      <details className="tutorial-transcript section-block">
        <summary>Read the complete narration transcript</summary>
        <div>
          <p>Imagine a factory for difficult problems. The useful part isn&apos;t asking an agent for an answer. It&apos;s knowing exactly what must be true before any answer earns trust.</p>
          <p>The hangar begins with one hundred bounded workbenches across nine domains. Every station starts with an external truth condition, a reference benchmark, a hard pass gate, and an economic or physical guardrail. Pick a problem by what can be measured, not by how exciting a claim sounds.</p>
          <p>Here we open workbench zero zero one: general-purpose lossless compression. Its job is precise. Reconstruct every file identically. Measure compressed bytes, speed, memory, and energy. Then compare the result against pinned reference tools. A clever idea that cannot clear those gates stays a recorded attempt.</p>
          <p>The shift board is where the factory itself is built and tested. An operator creates a construction or synthetic commissioning order, defines the bounded task and its done condition, and claims it under their own identity. The order can move only through explicit, revision-checked commands: open, claimed, in progress, review, then completed—or blocked with a reason.</p>
          <p>Runner interfaces are registered separately. Each runner states what it is allowed to execute and the trust assumptions around it. In this first hangar, runners are commissioning-only. They cannot upload arbitrary code, dispatch live research, or mark themselves promotion grade.</p>
          <p>Every change creates a new append-only history event. Corrections never erase earlier work. A failed attempt, a blocked route, or a disagreement remains searchable, so future people and agents don&apos;t pay to explore the same dead end without knowing it.</p>
          <p>And here is the most important guardrail. Completing a synthetic work order proves only that the factory plumbing worked. It is not scientific evidence. It is not an independent reproduction. It cannot promote a result.</p>
          <p>The scientific control plane is deliberately separate. When that lane is built, a claim can begin blind validation by two different people and their agents, starting from zero evidence and zero reproductions. The hangar may propose a handoff. It cannot approve its own science.</p>
          <p>That is the workflow: bound the problem, define the gates, attribute the work, constrain the runner, preserve every attempt, and keep promotion outside the system that produced the claim. The factory doesn&apos;t promise instant breakthroughs. It makes genuine progress legible, repeatable, and harder to fake.</p>
        </div>
      </details>
    </>
  );
}
