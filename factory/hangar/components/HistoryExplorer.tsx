"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import type { ActivityEvent, OperatingMode } from "@/lib/factory-types";
import correctionExample from "@/data/correction-history-example.json";

async function readJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) throw new Error(body.error ?? "Request failed.");
  return body;
}

async function loadHistory(searchQuery: string, searchMode: OperatingMode | "") {
  const params = new URLSearchParams();
  if (searchQuery.trim()) params.set("q", searchQuery.trim());
  if (searchMode) params.set("mode", searchMode);
  const body = await readJson<{ activity: ActivityEvent[] }>(
    await fetch(`/api/history?${params}`, { cache: "no-store" }),
  );
  return body.activity;
}

export function HistoryExplorer() {
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<OperatingMode | "">("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const search = useCallback(async (searchQuery = query, searchMode = mode) => {
    setLoading(true);
    setError("");
    try {
      setActivity(await loadHistory(searchQuery, searchMode));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "History unavailable.");
    } finally {
      setLoading(false);
    }
  }, [mode, query]);

  useEffect(() => {
    let active = true;
    loadHistory("", "")
      .then((loaded) => { if (active) setActivity(loaded); })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "History unavailable.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    search().catch(() => undefined);
  }

  return (
    <>
      <form className="history-search" onSubmit={submit}>
        <label><span>Search append-only activity</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Order ID, operator, state, runner…" /></label>
        <label><span>Mode</span><select value={mode} onChange={(event) => setMode(event.target.value as OperatingMode | "")}><option value="">All hangar activity</option><option value="HANGAR_CONSTRUCTION">Construction</option><option value="SYNTHETIC_COMMISSIONING">Synthetic commissioning</option></select></label>
        <button className="button button-primary" type="submit">Search log</button>
      </form>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="history-boundary"><span>DB invariant</span><strong>UPDATE and DELETE rejected</strong><p>This is operational provenance, not the scientific hash-chain ledger.</p></div>
      <section className="correction-register" aria-labelledby="correction-register-title">
        <div className="correction-register-head">
          <div>
            <span className="eyebrow">Verified static projection / synthetic only</span>
            <h2 id="correction-register-title">Original history and current standing coexist.</h2>
          </div>
          <dl>
            <div><dt>Original</dt><dd>{correctionExample.originalStanding}</dd></div>
            <div><dt>Current</dt><dd>{correctionExample.currentStanding}</dd></div>
            <div><dt>Original bytes</dt><dd>{correctionExample.originalBytesPreserved ? "PRESERVED" : "MISSING"}</dd></div>
          </dl>
        </div>
        <p className="correction-target mono">
          {correctionExample.target.artifactClass} / {correctionExample.target.artifactId} / sha256:{correctionExample.target.artifactSha256}
        </p>
        <ol className="correction-timeline">
          {correctionExample.records.map((record) => (
            <li key={record.correctionId}>
              <span className="correction-step mono">#{String(record.sequence).padStart(2, "0")}</span>
              <div>
                <div className="card-topline"><span>{record.action}</span><span>{record.standingBefore} &rarr; {record.standingAfter}</span></div>
                <h3>{record.publicSummary}</h3>
                <p className="mono">{record.correctionId} / sha256:{record.recordSha256}</p>
              </div>
              <time>{new Date(record.recordedAt).toLocaleString("en-GB")}</time>
            </li>
          ))}
        </ol>
        <div className="correction-boundary"><strong>NO SCIENTIFIC STANDING</strong><span>The engine ledger is authoritative; this Hangar panel is a read-only synthetic projection.</span></div>
      </section>
      {loading ? <div className="empty-state"><strong>Reading activity stream…</strong></div> : activity.length === 0 ? <div className="empty-state"><span className="mono">NO MATCHES</span><strong>No activity events found.</strong><p>Failed and disputed commissioning work will remain visible once recorded.</p></div> : <div className="history-list">{activity.map((event) => <article key={event.eventId}><div className="history-sequence mono">#{String(event.sequence).padStart(5, "0")}</div><div className="history-main"><div className="card-topline"><span className={event.mode === "SYNTHETIC_COMMISSIONING" ? "status-dot status-dot-amber" : "status-dot status-dot-green"} /><span>{event.mode.replaceAll("_", " ")}</span><span>{event.eventType}</span></div><h3>{event.summary}</h3><p><span>{event.actorDisplay}</span><span>{event.entityType} / {event.entityId} / v{event.entityVersion}</span></p></div><div className="history-time"><time>{new Date(event.createdAt).toLocaleDateString("en-GB")}</time><span>{new Date(event.createdAt).toLocaleTimeString("en-GB")}</span><strong>NO SCIENTIFIC STANDING</strong></div></article>)}</div>}
    </>
  );
}
