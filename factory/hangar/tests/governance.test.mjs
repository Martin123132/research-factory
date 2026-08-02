import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const baseUrl = process.env.HANGAR_TEST_URL;
if (!baseUrl) throw new Error("HANGAR_TEST_URL is required.");
const identityHeaders = {
  "content-type": "application/json",
  "oai-authenticated-user-id": "test-platform-user",
  "oai-authenticated-user-email": "operator@example.invalid",
};

async function post(path, body, headers = identityHeaders) {
  return fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

test("the hangar API rejects live research mode structurally", async () => {
  const response = await post("/api/work-orders", {
    workbenchId: 1,
    mode: "LIVE_RESEARCH",
    title: "Attempt a live result",
    description: "This must never reach D1.",
  });
  assert.equal(response.status, 422);
  const body = await response.json();
  assert.equal(body.boundary.scientificEvidence, false);
  assert.equal(body.boundary.countsAsIndependentReproduction, false);
  assert.equal(body.boundary.eligibleForPromotion, false);
});

test("client-supplied promotion fields are rejected", async () => {
  const response = await post("/api/work-orders", {
    workbenchId: 1,
    mode: "SYNTHETIC_COMMISSIONING",
    title: "Commission work-order form",
    description: "Known synthetic fixture only.",
    eligibleForPromotion: true,
  });
  assert.equal(response.status, 400);
  assert.match((await response.json()).error, /Unsupported field/i);
});

test("promotion-grade runners cannot be registered", async () => {
  const response = await post("/api/runners", {
    label: "Forbidden evaluator",
    trustClass: "PROMOTION_GRADE",
    notes: "Must be rejected before database access.",
  });
  assert.equal(response.status, 422);
});

test("arbitrary work-order status writes are not an API surface", async () => {
  const response = await post("/api/work-orders/WO-TEST/command", {
    command: "SET_STATUS",
    expectedRevision: 0,
    note: "",
  });
  assert.equal(response.status, 400);
  assert.match((await response.json()).error, /Unknown work-order command/i);
});

test("the tracked migration enforces the non-scientific and append-only boundary", async () => {
  const sql = await readFile(
    new URL("../drizzle/0000_glorious_screwball.sql", import.meta.url),
    "utf8",
  );
  assert.match(sql, /scientific_evidence[^\n]+CHECK \(`scientific_evidence` = 0\)/);
  assert.match(sql, /counts_as_independent_reproduction[^\n]+CHECK/);
  assert.match(sql, /eligible_for_promotion[^\n]+CHECK/);
  assert.match(sql, /activity_events_reject_update/);
  assert.match(sql, /activity_events_reject_delete/);
  assert.match(sql, /CREATE UNIQUE INDEX `activity_events_entity_version_idx`/);
  assert.doesNotMatch(sql, /RESULT_SUBMITTED|RERUN_SUBMITTED|PROMOTED/);
});
