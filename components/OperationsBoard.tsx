"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ScopeNotice } from "./ScopeNotice";
import type {
  Actor,
  OperatingMode,
  WorkOrder,
  WorkOrderCommand,
  WorkOrderStatus,
} from "@/lib/factory-types";

type StationOption = { id: number; code: string; title: string };

const COMMANDS: Record<
  WorkOrderStatus,
  { command: WorkOrderCommand; label: string; tone?: "danger" | "quiet" }[]
> = {
  OPEN: [{ command: "CLAIM", label: "Claim order" }],
  CLAIMED: [
    { command: "START", label: "Start work" },
    { command: "RELEASE", label: "Release", tone: "quiet" },
  ],
  IN_PROGRESS: [
    { command: "REQUEST_REVIEW", label: "Ready for review" },
    { command: "BLOCK", label: "Mark blocked", tone: "danger" },
    { command: "RELEASE", label: "Release", tone: "quiet" },
  ],
  BLOCKED: [
    { command: "RESUME", label: "Resume" },
    { command: "RELEASE", label: "Release", tone: "quiet" },
  ],
  REVIEW: [
    { command: "COMPLETE", label: "Close work order" },
    { command: "RETURN_TO_WORK", label: "Return to work", tone: "quiet" },
  ],
  COMPLETED: [],
};

async function responseJson<T>(response: Response): Promise<T> {
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok) throw new Error(body.error ?? "Request failed.");
  return body;
}

async function loadOperations() {
  const [ordersResponse, sessionResponse] = await Promise.all([
    fetch("/api/work-orders", { cache: "no-store" }),
    fetch("/api/session", { cache: "no-store" }),
  ]);
  const orderData = await responseJson<{ workOrders: WorkOrder[] }>(ordersResponse);
  const sessionData = await responseJson<{ actor: Actor | null }>(sessionResponse);
  return { orders: orderData.workOrders, actor: sessionData.actor };
}

function statusLabel(status: WorkOrderStatus) {
  return status.replaceAll("_", " ").toLowerCase();
}

export function OperationsBoard({
  stations,
  initialWorkbenchId,
}: {
  stations: StationOption[];
  initialWorkbenchId: number;
}) {
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [actor, setActor] = useState<Actor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [mode, setMode] = useState<OperatingMode>("SYNTHETIC_COMMISSIONING");
  const [workbenchId, setWorkbenchId] = useState(initialWorkbenchId);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});

  const stationMap = useMemo(
    () => new Map(stations.map((station) => [station.id, station])),
    [stations],
  );

  const refresh = useCallback(async () => {
    const data = await loadOperations();
    setOrders(data.orders);
    setActor(data.actor);
    if (data.actor?.assurance === "PLATFORM_HEADER") {
      setMode((current) => current === "SYNTHETIC_COMMISSIONING" ? "HANGAR_CONSTRUCTION" : current);
    }
  }, []);

  useEffect(() => {
    let active = true;
    loadOperations()
      .then((data) => {
        if (!active) return;
        setOrders(data.orders);
        setActor(data.actor);
        if (data.actor?.assurance === "PLATFORM_HEADER") {
          setMode("HANGAR_CONSTRUCTION");
        }
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Shift board unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  async function createOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    try {
      await responseJson(
        await fetch("/api/work-orders", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ workbenchId, mode, title, description }),
        }),
      );
      setTitle("");
      setDescription("");
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the order.");
    } finally {
      setBusy("");
    }
  }

  async function sendCommand(order: WorkOrder, command: WorkOrderCommand) {
    const key = `${order.id}:${command}`;
    setBusy(key);
    setError("");
    try {
      await responseJson(
        await fetch(`/api/work-orders/${order.id}/command`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            command,
            expectedRevision: order.revision,
            note: notes[order.id] ?? "",
          }),
        }),
      );
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not move the order.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <ScopeNotice />
      <section className="operations-layout">
        <aside className="creation-panel">
          <div className="panel-title"><p className="eyebrow">New work order</p><h2>Put a job on the bench</h2></div>
          <form onSubmit={createOrder} className="stack-form">
            <label><span>Station</span><select value={workbenchId} onChange={(event) => setWorkbenchId(Number(event.target.value))}>{stations.map((station) => <option value={station.id} key={station.id}>{station.code} — {station.title}</option>)}</select></label>
            <label><span>Operating mode</span><select value={mode} onChange={(event) => setMode(event.target.value as OperatingMode)}><option value="HANGAR_CONSTRUCTION" disabled={actor?.assurance !== "PLATFORM_HEADER"}>Hangar construction</option><option value="SYNTHETIC_COMMISSIONING">Synthetic commissioning</option></select><small>{actor?.assurance === "LOCAL_PREVIEW" ? "Local preview is restricted to synthetic commissioning." : "Construction changes are attributed to your platform identity."}</small></label>
            <label><span>Order title</span><input required minLength={4} maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Draft the benchmark manifest" /></label>
            <label><span>Construction brief</span><textarea maxLength={1200} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Define the bounded piece of hangar work and its done condition." rows={5} /></label>
            <button className="button button-primary button-full" disabled={busy === "create" || !actor} type="submit">{busy === "create" ? "Writing order…" : "Create open order"}</button>
          </form>
          <div className="identity-readout"><span className={actor ? "operator-light online" : "operator-light"} /><div><small>Mutation identity</small><strong>{actor?.displayName ?? "Authentication unavailable"}</strong><span>{actor?.assurance.replaceAll("_", " ").toLowerCase()}</span></div></div>
        </aside>

        <div className="shift-board">
          <div className="section-heading compact-heading"><div><p className="eyebrow">Shift board</p><h2>{orders.length} operational orders</h2></div><button type="button" className="text-button" onClick={() => refresh().catch(() => undefined)}>Refresh</button></div>
          {error && <div className="error-banner" role="alert">{error}</div>}
          {loading ? (
            <div className="empty-state"><strong>Loading the shift ledger…</strong></div>
          ) : orders.length === 0 ? (
            <div className="empty-state"><span className="mono">CLEAR FLOOR</span><strong>No operational work orders yet.</strong><p>Create a construction order after sign-in, or a synthetic commissioning order in local preview.</p></div>
          ) : (
            <div className="order-list">
              {orders.map((order) => {
                const station = stationMap.get(order.workbenchId);
                const mine = !order.assigneeUserId || order.assigneeUserId === actor?.userId;
                return (
                  <article className={`order-card status-${order.status.toLowerCase()}`} key={order.id}>
                    <div className="order-status-line"><span className="status-pill">{statusLabel(order.status)}</span><span className="mode-pill">{order.mode === "SYNTHETIC_COMMISSIONING" ? "SYNTHETIC DRILL" : "CONSTRUCTION"}</span><span className="mono">r{order.revision}</span></div>
                    <div className="order-body"><div><p className="eyebrow">{station?.code ?? `WB-${order.workbenchId}`} / {order.id}</p><h3>{order.title}</h3><p>{order.description || "No additional construction notes."}</p></div><dl><div><dt>Owner</dt><dd>{order.assigneeDisplay ?? "Unclaimed"}</dd></div><div><dt>Updated</dt><dd>{new Date(order.updatedAt).toLocaleString("en-GB")}</dd></div><div><dt>Scientific standing</dt><dd>None</dd></div></dl></div>
                    {order.blockedReason && <p className="blocked-reason"><strong>Blocker:</strong> {order.blockedReason}</p>}
                    {order.status === "IN_PROGRESS" && mine && <textarea className="inline-note" rows={2} maxLength={600} value={notes[order.id] ?? ""} onChange={(event) => setNotes((current) => ({ ...current, [order.id]: event.target.value }))} placeholder="Required only when marking this order blocked." />}
                    <div className="order-actions">
                      {COMMANDS[order.status].map((action) => (
                        <button type="button" key={action.command} disabled={!mine || Boolean(busy)} onClick={() => sendCommand(order, action.command)} className={action.tone === "danger" ? "action-button danger" : action.tone === "quiet" ? "action-button quiet" : "action-button"}>{busy === `${order.id}:${action.command}` ? "Working…" : action.label}</button>
                      ))}
                      {!mine && <span className="owned-note">Claimed by another operator</span>}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
