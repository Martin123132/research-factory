"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import type { RunnerProfile, RunnerTrustClass } from "@/lib/factory-types";

async function readJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) throw new Error(body.error ?? "Request failed.");
  return body;
}

function trustLabel(value: RunnerTrustClass) {
  return value === "LOCAL_TRUSTED_CODE_ONLY"
    ? "Local · trusted code only"
    : "Container prototype · commissioning only";
}

async function loadRunners() {
  const body = await readJson<{ runners: RunnerProfile[] }>(
    await fetch("/api/runners", { cache: "no-store" }),
  );
  return body.runners;
}

export function RunnerRegistry() {
  const [runners, setRunners] = useState<RunnerProfile[]>([]);
  const [label, setLabel] = useState("");
  const [trustClass, setTrustClass] = useState<RunnerTrustClass>("LOCAL_TRUSTED_CODE_ONLY");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setRunners(await loadRunners());
  }, []);

  useEffect(() => {
    let active = true;
    loadRunners()
      .then((loaded) => { if (active) setRunners(loaded); })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Runner registry unavailable.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await readJson(
        await fetch("/api/runners", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ label, trustClass, notes }),
        }),
      );
      setLabel("");
      setNotes("");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not register the runner.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="operations-layout runner-layout">
      <aside className="creation-panel">
        <div className="panel-title"><p className="eyebrow">Runner registration</p><h2>Record an interface</h2></div>
        <form className="stack-form" onSubmit={submit}>
          <label><span>Runner label</span><input required minLength={3} maxLength={100} value={label} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. WB-001 Docker commissioning host" /></label>
          <label><span>Trust class</span><select value={trustClass} onChange={(event) => setTrustClass(event.target.value as RunnerTrustClass)}><option value="LOCAL_TRUSTED_CODE_ONLY">Local — trusted code only</option><option value="CONTAINER_COMMISSIONING_ONLY">Container prototype — commissioning only</option></select></label>
          <label><span>Interface notes</span><textarea rows={5} maxLength={800} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Runtime, adapter, isolation assumptions, and intended commissioning use." /></label>
          <button className="button button-primary button-full" disabled={busy} type="submit">{busy ? "Registering…" : "Register commissioning runner"}</button>
        </form>
        <div className="locked-option"><span>Promotion-grade runner</span><strong>Not available in Hangar 01</strong><p>A future evaluator requires a separate host, signed attestations, and a new authorization boundary.</p></div>
      </aside>
      <div className="shift-board">
        <div className="section-heading compact-heading"><div><p className="eyebrow">Registered interfaces</p><h2>{runners.length} commissioning runners</h2></div><button className="text-button" type="button" onClick={() => refresh().catch(() => undefined)}>Refresh</button></div>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {loading ? <div className="empty-state"><strong>Loading runner registry…</strong></div> : runners.length === 0 ? <div className="empty-state"><span className="mono">NO EXECUTION PLANE</span><strong>No runners registered yet.</strong><p>Registration records an interface and its trust boundary. It does not dispatch code.</p></div> : <div className="runner-grid">{runners.map((runner) => <article className="runner-card" key={runner.id}><div className="card-topline"><span className="status-dot status-dot-green" /><span>REGISTERED</span><span className="mono">{runner.id}</span></div><h3>{runner.label}</h3><p>{runner.notes || "No interface notes supplied."}</p><dl><div><dt>Trust</dt><dd>{trustLabel(runner.trustClass)}</dd></div><div><dt>Owner</dt><dd>{runner.ownerDisplay}</dd></div><div><dt>Promotion eligible</dt><dd className="danger-text">No</dd></div></dl></article>)}</div>}
      </div>
    </section>
  );
}
