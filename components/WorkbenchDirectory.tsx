"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Workbench } from "@/lib/workbenches";
import {
  workbenchCode,
  workbenchReadiness,
  workbenchStatusDot,
} from "@/lib/workbenches";

export function WorkbenchDirectory({
  items,
  initialCategory,
}: {
  items: Workbench[];
  initialCategory?: string;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(initialCategory ?? "ALL");
  const [lane, setLane] = useState("ALL");
  const categories = useMemo(
    () => Array.from(new Set(items.map((item) => item.short_category))).sort(),
    [items],
  );
  const lanes = useMemo(
    () => Array.from(new Set(items.map((item) => item.evidence_lane))).sort(),
    [items],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchesQuery =
        !needle ||
        [
          item.workbench,
          item.benchmark,
          item.category,
          item.hard_gate_and_score,
          workbenchCode(item.id),
        ]
          .join(" ")
          .toLowerCase()
          .includes(needle);
      return (
        matchesQuery &&
        (category === "ALL" || item.short_category === category) &&
        (lane === "ALL" || item.evidence_lane === lane)
      );
    });
  }, [items, query, category, lane]);

  return (
    <>
      <div className="filter-bar">
        <label className="search-field">
          <span>Search stations</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Compression, routing, mass gap…"
          />
        </label>
        <label>
          <span>Domain</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="ALL">All domains</option>
            {categories.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label>
          <span>Evidence lane</span>
          <select value={lane} onChange={(event) => setLane(event.target.value)}>
            <option value="ALL">All lanes</option>
            {lanes.map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <div className="filter-count"><strong>{visible.length}</strong><span>of 100 shown</span></div>
      </div>
      <div className="workbench-grid">
        {visible.map((item) => (
          <article className="workbench-card" key={item.id}>
            <div className="card-topline">
              <span className={workbenchStatusDot(item)} />
              <span>{workbenchReadiness(item)}</span>
              <span className="mono">{workbenchCode(item.id)}</span>
            </div>
            <p className="workbench-domain">{item.short_category} · {item.evidence_lane}</p>
            <h2>{item.workbench}</h2>
            <p className="workbench-benchmark"><span>Reference benchmark</span>{item.benchmark}</p>
            <p className="workbench-gate">{item.hard_gate_and_score}</p>
            <Link className="card-link" href={`/workbenches/${item.id}`}>
              Open station brief <span>→</span>
            </Link>
          </article>
        ))}
      </div>
      {visible.length === 0 && (
        <div className="empty-state">
          <strong>No station matches those filters.</strong>
          <button type="button" onClick={() => { setQuery(""); setCategory("ALL"); setLane("ALL"); }}>
            Clear filters
          </button>
        </div>
      )}
    </>
  );
}
