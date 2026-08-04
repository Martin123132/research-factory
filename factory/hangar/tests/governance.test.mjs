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

async function get(path) {
  return fetch(`${baseUrl}${path}`, { headers: identityHeaders });
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
  const initialSql = await readFile(
    new URL("../drizzle/0000_glorious_screwball.sql", import.meta.url),
    "utf8",
  );
  const shiftSql = await readFile(
    new URL("../drizzle/0001_remarkable_fat_cobra.sql", import.meta.url),
    "utf8",
  );
  assert.match(initialSql, /scientific_evidence[^\n]+CHECK \(`scientific_evidence` = 0\)/);
  assert.match(initialSql, /counts_as_independent_reproduction[^\n]+CHECK/);
  assert.match(initialSql, /eligible_for_promotion[^\n]+CHECK/);
  assert.match(initialSql, /activity_events_reject_update/);
  assert.match(initialSql, /activity_events_reject_delete/);
  assert.match(initialSql, /CREATE UNIQUE INDEX `activity_events_entity_version_idx`/);
  assert.doesNotMatch(initialSql, /RESULT_SUBMITTED|RERUN_SUBMITTED|PROMOTED/);
  assert.match(shiftSql, /CREATE TABLE `shift_reports`/);
  assert.match(shiftSql, /shift_reports_no_evidence_check/);
  assert.match(shiftSql, /shift_reports_no_reproduction_check/);
  assert.match(shiftSql, /shift_reports_no_promotion_check/);
  assert.match(shiftSql, /shift_reports_no_completion_check/);
  assert.match(shiftSql, /shift_reports_reject_update/);
  assert.match(shiftSql, /shift_reports_reject_delete/);
  assert.match(shiftSql, /shift_reports_enforce_chain/);
  assert.match(shiftSql, /shift_reports_work_order_sequence_idx/);
  assert.doesNotMatch(shiftSql, /DROP TABLE|RESULT_SUBMITTED|RERUN_SUBMITTED|PROMOTED/);
});

test("shift reports append a hash chain without moving or closing the work order", async () => {
  const createdResponse = await post("/api/work-orders", {
    workbenchId: 1,
    mode: "SYNTHETIC_COMMISSIONING",
    title: "Exercise append-only shift reports",
    description: "Synthetic CT-004 integration fixture.",
  });
  assert.equal(createdResponse.status, 201);
  let order = (await createdResponse.json()).workOrder;

  let commandResponse = await post(`/api/work-orders/${order.id}/command`, {
    command: "CLAIM",
    expectedRevision: order.revision,
    note: "",
  });
  assert.equal(commandResponse.status, 200);
  order = (await commandResponse.json()).workOrder;
  commandResponse = await post(`/api/work-orders/${order.id}/command`, {
    command: "START",
    expectedRevision: order.revision,
    note: "",
  });
  assert.equal(commandResponse.status, 200);
  order = (await commandResponse.json()).workOrder;
  assert.equal(order.status, "IN_PROGRESS");
  const stableRevision = order.revision;

  const baseDraft = {
    expectedRevision: stableRevision,
    startedAt: "2026-08-04T09:00:00Z",
    endedAt: "2026-08-04T13:00:00Z",
    attemptedWork: [
      {
        approach: "Exercise the synthetic append-only report path.",
        result: "The operational endpoint accepted a bounded report.",
        decision: "CONTINUE",
      },
    ],
    observations: ["The work-order revision remained unchanged."],
    artifactReferences: [],
    blockers: [],
    nextLeads: [
      {
        lead: "Append a second report.",
        rationale: "This exercises the previous-report hash link.",
      },
    ],
  };
  const firstResponse = await post(`/api/work-orders/${order.id}/shift-reports`, {
    ...baseDraft,
    outcomeClass: "PROGRESS",
  });
  assert.equal(firstResponse.status, 201);
  const first = (await firstResponse.json()).shiftReport;
  assert.equal(first.reportSequence, 1);
  assert.equal(first.previousReportSha256, null);
  assert.match(first.reportSha256, /^[0-9a-f]{64}$/);
  assert.equal(first.workOrderSnapshot.revision, stableRevision);
  assert.deepEqual(first.boundary, {
    scope: "HANGAR_OPERATIONS_ONLY",
    scientificEvidence: false,
    countsAsIndependentReproduction: false,
    eligibleForPromotion: false,
    closesWorkOrder: false,
    operationalRecordOnly: true,
  });

  const secondResponse = await post(`/api/work-orders/${order.id}/shift-reports`, {
    ...baseDraft,
    outcomeClass: "NO_GAIN",
    attemptedWork: [
      {
        approach: "Repeat the same bounded construction probe.",
        result: "The repeated probe added no new operational information.",
        decision: "ABANDON",
      },
    ],
    observations: ["The duplicate direction is now recorded for later workers."],
  });
  assert.equal(secondResponse.status, 201);
  const second = (await secondResponse.json()).shiftReport;
  assert.equal(second.reportSequence, 2);
  assert.equal(second.previousReportSha256, first.reportSha256);

  const reportsResponse = await get(`/api/work-orders/${order.id}/shift-reports`);
  assert.equal(reportsResponse.status, 200);
  const reports = (await reportsResponse.json()).shiftReports;
  assert.equal(reports.length, 2);
  assert.equal(reports[0].reportSha256, first.reportSha256);
  assert.equal(reports[1].previousReportSha256, first.reportSha256);

  const ordersResponse = await get("/api/work-orders");
  assert.equal(ordersResponse.status, 200);
  const unchanged = (await ordersResponse.json()).workOrders.find(
    (candidate) => candidate.id === order.id,
  );
  assert.equal(unchanged.status, "IN_PROGRESS");
  assert.equal(unchanged.revision, stableRevision);
  assert.equal(unchanged.completedAt, null);
});

test("shift-report intake rejects verdict and standing fields", async () => {
  for (const forbidden of ["validatorVerdict", "liveResearch", "scientificEvidence"]) {
    const response = await post("/api/work-orders/WO-NOT-REACHED/shift-reports", {
      expectedRevision: 0,
      outcomeClass: "PROGRESS",
      startedAt: "2026-08-04T09:00:00Z",
      endedAt: "2026-08-04T10:00:00Z",
      attemptedWork: [
        { approach: "Attempt a forbidden field.", result: "Rejected.", decision: "ABANDON" },
      ],
      observations: ["The request must fail before database access."],
      artifactReferences: [],
      blockers: [],
      nextLeads: [],
      [forbidden]: true,
    });
    assert.equal(response.status, 400);
    assert.match((await response.json()).error, /Unsupported field/i);
  }
});

test("shift-report artifact references cannot carry inline or private material", async () => {
  const draft = {
    expectedRevision: 0,
    outcomeClass: "PROGRESS",
    startedAt: "2026-08-04T09:00:00Z",
    endedAt: "2026-08-04T10:00:00Z",
    attemptedWork: [
      { approach: "Inspect a provenance reference.", result: "Rejected.", decision: "ABANDON" },
    ],
    observations: ["The request must fail before database access."],
    blockers: [],
    nextLeads: [],
  };
  const inlineResponse = await post("/api/work-orders/WO-NOT-REACHED/shift-reports", {
    ...draft,
    artifactReferences: [
      {
        kind: "REPOSITORY_PATH",
        locator: "factory/public/log.txt",
        sha256: "a".repeat(64),
        mediaType: "text/plain",
        purpose: "Synthetic provenance",
        inlineContent: "forbidden bytes",
      },
    ],
  });
  assert.equal(inlineResponse.status, 400);
  assert.match((await inlineResponse.json()).error, /Unsupported field/i);

  const privateResponse = await post("/api/work-orders/WO-NOT-REACHED/shift-reports", {
    ...draft,
    artifactReferences: [
      {
        kind: "REPOSITORY_PATH",
        locator: "factory/private/hidden-answer.json",
        sha256: "b".repeat(64),
        mediaType: "application/json",
        purpose: "Must not be accepted",
      },
    ],
  });
  assert.equal(privateResponse.status, 400);
  assert.match((await privateResponse.json()).error, /public paths/i);
});
