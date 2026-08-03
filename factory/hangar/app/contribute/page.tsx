import type { Metadata } from "next";
import Link from "next/link";
import { ScopeNotice } from "@/components/ScopeNotice";

export const metadata: Metadata = {
  title: "Contribute to construction",
  description:
    "A credential-neutral, construction-only route into the Research Factory.",
};

const repository = "https://github.com/Martin123132/research-factory";

export default function ContributePage() {
  return (
    <>
      <section className="page-heading page-heading-row">
        <div>
          <p className="eyebrow">Contributor entrance / construction only</p>
          <h1>Clock in. Leave the bench clearer than you found it.</h1>
          <p>
            Pick one bounded job, declare what you used, run the stated checks and
            hand the next worker a reproducible log. Degrees, prestige and paid legal
            advice are not entry requirements.
          </p>
        </div>
        <div className="page-status-card">
          <span>PUBLIC LANE</span>
          <strong>CONSTRUCTION</strong>
          <small>Scientific promotion remains locked</small>
        </div>
      </section>

      <ScopeNotice />

      <section className="contributor-flow" aria-label="Construction contribution flow">
        <article>
          <span className="flow-index">01</span>
          <p className="eyebrow">Choose</p>
          <h2>Take one defined task</h2>
          <p>Exact paths, a definition of done, known blockers and repeatable checks.</p>
        </article>
        <i>→</i>
        <article>
          <span className="flow-index">02</span>
          <p className="eyebrow">Build</p>
          <h2>Work in the open</h2>
          <p>Record sources, AI assistance, trade-offs and useful failed directions.</p>
        </article>
        <i>→</i>
        <article>
          <span className="flow-index">03</span>
          <p className="eyebrow">Check</p>
          <h2>Run the declared gate</h2>
          <p>A failure is logged honestly. A polished explanation cannot replace evidence.</p>
        </article>
        <i>→</i>
        <article>
          <span className="flow-index">04</span>
          <p className="eyebrow">Hand off</p>
          <h2>Open a signed pull request</h2>
          <p>You retain ownership; the path licence gives others permission to continue.</p>
        </article>
      </section>

      <section className="contributor-actions section-block">
        <article className="contributor-action-card contributor-action-primary">
          <p className="eyebrow">Ready to pick up a job?</p>
          <h2>Start from a construction packet</h2>
          <p>
            Browse bounded jobs or propose a missing piece with the structured task form.
            Public issues cannot accept hidden answers, confidential inventions or validator
            verdicts.
          </p>
          <div className="button-row">
            <a
              className="button button-primary"
              href={`${repository}/issues?q=is%3Aissue+is%3Aopen+label%3Ahangar-construction`}
              target="_blank"
              rel="noreferrer"
            >
              Browse open construction
            </a>
            <a
              className="button button-secondary"
              href={`${repository}/issues/new?template=construction-task.yml`}
              target="_blank"
              rel="noreferrer"
            >
              Define a bounded task
            </a>
            <a
              className="button button-secondary"
              href={`${repository}/blob/main/CONSTRUCTION_BACKLOG.md`}
              target="_blank"
              rel="noreferrer"
            >
              View starter task packets
            </a>
          </div>
        </article>

        <article className="contributor-action-card">
          <p className="eyebrow">Already inside the Hangar?</p>
          <h2>Mirror the job on the shift board</h2>
          <p>
            Claiming and moving a Hangar work order creates attributed operational history.
            That history is design provenance only and can never become scientific credit.
          </p>
          <Link className="button button-secondary" href="/operations">
            Open the shift board
          </Link>
        </article>
      </section>

      <section className="section-block contributor-rules">
        <div className="section-heading">
          <div>
            <p className="eyebrow">What the licence map means</p>
            <h2>Your work stays yours</h2>
          </div>
        </div>
        <div className="architecture-grid">
          <article>
            <span className="architecture-tag">CODE</span>
            <h3>Apache-2.0</h3>
            <p>Factory software, schemas, automation and non-scientific tooling.</p>
          </article>
          <article>
            <span className="architecture-tag">EXPLANATION</span>
            <h3>CC BY 4.0</h3>
            <p>Authored protocols, documentation, station descriptions and project media.</p>
          </article>
          <article>
            <span className="architecture-tag">FACTS</span>
            <h3>CC0 1.0</h3>
            <p>Factory-created hashes, measurements, manifests and synthetic public data.</p>
          </article>
          <article>
            <span className="architecture-tag">CANDIDATES</span>
            <h3>No inherited licence</h3>
            <p>Future research artifacts require their own licence or a metadata-only record.</p>
          </article>
        </div>
      </section>

      <section className="contributor-stop-panel">
        <div>
          <p className="eyebrow">Stop before upload</p>
          <h2>Keep secrets, hidden answers and unfiled inventions off the public floor.</h2>
          <p>
            If you are unsure whether you may share something, continue without depositing
            the protected artifact. Metadata-only is a valid boundary; guessing permission is
            not.
          </p>
        </div>
        <a
          className="button button-secondary"
          href={`${repository}/blob/main/CONTRIBUTOR_QUICKSTART.md`}
          target="_blank"
          rel="noreferrer"
        >
          Read the complete quickstart
        </a>
      </section>
    </>
  );
}
