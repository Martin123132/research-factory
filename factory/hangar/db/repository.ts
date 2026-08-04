import { ensureHangarDatabase } from "./bootstrap";
import { getD1 } from "./index";
import type {
  ActivityEvent,
  Actor,
  OperatingMode,
  RunnerProfile,
  RunnerTrustClass,
  ShiftReport,
  ShiftReportDraft,
  WorkOrder,
  WorkOrderCommand,
  WorkOrderStatus,
} from "@/lib/factory-types";
import { nextStatusForCommand } from "@/lib/factory-types";
import { canonicalJson, sha256Canonical } from "@/lib/canonical-json";

type WorkOrderRow = {
  id: string;
  workbench_id: number;
  mode: OperatingMode;
  title: string;
  description: string;
  status: WorkOrderStatus;
  assignee_user_id: string | null;
  assignee_display: string | null;
  created_by_user_id: string;
  created_by_display: string;
  blocked_reason: string | null;
  scientific_evidence: number;
  counts_as_independent_reproduction: number;
  eligible_for_promotion: number;
  revision: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

type RunnerRow = {
  id: string;
  label: string;
  trust_class: RunnerTrustClass;
  status: "REGISTERED";
  notes: string;
  promotion_eligible: number;
  owner_user_id: string;
  owner_display: string;
  created_at: string;
  updated_at: string;
};

type ActivityRow = {
  sequence: number;
  event_id: string;
  event_type: string;
  entity_type: "WORK_ORDER" | "RUNNER";
  entity_id: string;
  entity_version: number;
  mode: OperatingMode;
  actor_user_id: string;
  actor_display: string;
  summary: string;
  payload_json: string;
  scientific_evidence: number;
  counts_as_independent_reproduction: number;
  eligible_for_promotion: number;
  created_at: string;
};

type ShiftReportRow = {
  sequence: number;
  report_json: string;
};

export class FactoryRepositoryError extends Error {
  constructor(
    message: string,
    public status = 400,
  ) {
    super(message);
  }
}

function workOrderFromRow(row: WorkOrderRow): WorkOrder {
  return {
    id: row.id,
    workbenchId: row.workbench_id,
    mode: row.mode,
    title: row.title,
    description: row.description,
    status: row.status,
    assigneeUserId: row.assignee_user_id,
    assigneeDisplay: row.assignee_display,
    createdByUserId: row.created_by_user_id,
    createdByDisplay: row.created_by_display,
    blockedReason: row.blocked_reason,
    scientificEvidence: false,
    countsAsIndependentReproduction: false,
    eligibleForPromotion: false,
    revision: row.revision,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    completedAt: row.completed_at,
  };
}

function runnerFromRow(row: RunnerRow): RunnerProfile {
  return {
    id: row.id,
    label: row.label,
    trustClass: row.trust_class,
    status: row.status,
    notes: row.notes,
    promotionEligible: false,
    ownerUserId: row.owner_user_id,
    ownerDisplay: row.owner_display,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function activityFromRow(row: ActivityRow): ActivityEvent {
  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(row.payload_json) as Record<string, unknown>;
  } catch {
    payload = { parseError: true };
  }
  return {
    sequence: row.sequence,
    eventId: row.event_id,
    eventType: row.event_type,
    entityType: row.entity_type,
    entityId: row.entity_id,
    entityVersion: row.entity_version,
    mode: row.mode,
    actorUserId: row.actor_user_id,
    actorDisplay: row.actor_display,
    summary: row.summary,
    payload,
    scientificEvidence: false,
    countsAsIndependentReproduction: false,
    eligibleForPromotion: false,
    createdAt: row.created_at,
  };
}

function shiftReportFromRow(row: ShiftReportRow): ShiftReport {
  try {
    return JSON.parse(row.report_json) as ShiftReport;
  } catch {
    throw new FactoryRepositoryError(
      `Stored shift report at sequence ${row.sequence} is not valid JSON.`,
      500,
    );
  }
}

function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID().slice(0, 12).toUpperCase()}`;
}

function activityStatement(
  database: D1Database,
  input: {
    eventType: string;
    entityType: "WORK_ORDER" | "RUNNER";
    entityId: string;
    entityVersion: number;
    mode: OperatingMode;
    actor: Actor;
    summary: string;
    payload?: Record<string, unknown>;
    createdAt: string;
  },
) {
  return database
    .prepare(
      `INSERT INTO activity_events (
        event_id, event_type, entity_type, entity_id, entity_version, mode,
        actor_user_id, actor_display, summary, payload_json, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      makeId("EVT"),
      input.eventType,
      input.entityType,
      input.entityId,
      input.entityVersion,
      input.mode,
      input.actor.userId,
      input.actor.displayName,
      input.summary,
      JSON.stringify(input.payload ?? {}),
      input.createdAt,
    );
}

export async function listWorkOrders(limit = 100) {
  await ensureHangarDatabase();
  const database = getD1();
  const result = await database
    .prepare(
      `SELECT * FROM work_orders
       ORDER BY CASE status
         WHEN 'IN_PROGRESS' THEN 1
         WHEN 'BLOCKED' THEN 2
         WHEN 'REVIEW' THEN 3
         WHEN 'CLAIMED' THEN 4
         WHEN 'OPEN' THEN 5
         ELSE 6 END,
       updated_at DESC
       LIMIT ?`,
    )
    .bind(Math.min(Math.max(limit, 1), 250))
    .all<WorkOrderRow>();
  return result.results.map(workOrderFromRow);
}

export async function createWorkOrder(
  input: {
    workbenchId: number;
    mode: OperatingMode;
    title: string;
    description: string;
  },
  actor: Actor,
) {
  await ensureHangarDatabase();
  const database = getD1();
  const id = makeId("WO");
  const now = new Date().toISOString();
  const orderStatement = database
    .prepare(
      `INSERT INTO work_orders (
        id, workbench_id, mode, title, description, status,
        created_by_user_id, created_by_display, revision, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, 0, ?, ?)`,
    )
    .bind(
      id,
      input.workbenchId,
      input.mode,
      input.title,
      input.description,
      actor.userId,
      actor.displayName,
      now,
      now,
    );
  await database.batch([
    orderStatement,
    activityStatement(database, {
      eventType: "HANGAR_WORK_ORDER_CREATED",
      entityType: "WORK_ORDER",
      entityId: id,
      entityVersion: 0,
      mode: input.mode,
      actor,
      summary: `Created ${input.mode === "HANGAR_CONSTRUCTION" ? "construction" : "synthetic commissioning"} order ${id}`,
      payload: { workbenchId: input.workbenchId, title: input.title },
      createdAt: now,
    }),
  ]);

  return getWorkOrder(id);
}

export async function getWorkOrder(id: string) {
  await ensureHangarDatabase();
  const database = getD1();
  const row = await database
    .prepare("SELECT * FROM work_orders WHERE id = ?")
    .bind(id)
    .first<WorkOrderRow>();
  return row ? workOrderFromRow(row) : null;
}

export async function commandWorkOrder(
  id: string,
  command: WorkOrderCommand,
  expectedRevision: number,
  note: string,
  actor: Actor,
) {
  const current = await getWorkOrder(id);
  if (!current) throw new FactoryRepositoryError("Work order not found.", 404);
  if (current.revision !== expectedRevision) {
    throw new FactoryRepositoryError(
      "This order changed since it was loaded. Refresh and try again.",
      409,
    );
  }
  const nextStatus = nextStatusForCommand(current.status, command);
  if (!nextStatus) {
    throw new FactoryRepositoryError(
      `${command} is not available while the order is ${current.status}.`,
      409,
    );
  }
  if (
    current.status !== "OPEN" &&
    current.assigneeUserId &&
    current.assigneeUserId !== actor.userId
  ) {
    throw new FactoryRepositoryError(
      "Only the operator who claimed this order can move it.",
      403,
    );
  }
  if (nextStatus === "BLOCKED" && !note.trim()) {
    throw new FactoryRepositoryError("A blocked order needs a reason.", 400);
  }

  const nextAssigneeId =
    nextStatus === "CLAIMED"
      ? actor.userId
      : nextStatus === "OPEN"
        ? null
        : current.assigneeUserId;
  const nextAssigneeDisplay =
    nextStatus === "CLAIMED"
      ? actor.displayName
      : nextStatus === "OPEN"
        ? null
        : current.assigneeDisplay;
  const now = new Date().toISOString();
  const database = getD1();
  const updateStatement = database
    .prepare(
      `UPDATE work_orders
       SET status = ?, assignee_user_id = ?, assignee_display = ?,
           blocked_reason = ?, completed_at = ?, revision = revision + 1,
           updated_at = ?
       WHERE id = ? AND revision = ?`,
    )
    .bind(
      nextStatus,
      nextAssigneeId,
      nextAssigneeDisplay,
      nextStatus === "BLOCKED" ? note.trim() : null,
      nextStatus === "COMPLETED" ? now : null,
      now,
      id,
      expectedRevision,
    );

  const batchResult = await database.batch([
      updateStatement,
      activityStatement(database, {
        eventType: "HANGAR_WORK_ORDER_STATE_CHANGED",
        entityType: "WORK_ORDER",
        entityId: id,
        entityVersion: expectedRevision + 1,
        mode: current.mode,
        actor,
        summary: `${id} moved from ${current.status} to ${nextStatus}`,
        payload: {
          from: current.status,
          to: nextStatus,
          note: note.trim() || undefined,
          revision: expectedRevision + 1,
        },
        createdAt: now,
      }),
    ]).catch(() => {
      throw new FactoryRepositoryError(
        "This order changed concurrently. Refresh and try again.",
        409,
      );
    });

  if ((batchResult[0]?.meta.changes ?? 0) !== 1) {
    throw new FactoryRepositoryError(
      "This order changed concurrently. Refresh and try again.",
      409,
    );
  }

  return getWorkOrder(id);
}

export async function listShiftReports(workOrderId: string, limit = 100) {
  await ensureHangarDatabase();
  const database = getD1();
  const result = await database
    .prepare(
      `SELECT sequence, report_json FROM shift_reports
       WHERE work_order_id = ?
       ORDER BY report_sequence ASC
       LIMIT ?`,
    )
    .bind(workOrderId, Math.min(Math.max(limit, 1), 250))
    .all<ShiftReportRow>();
  return result.results.map(shiftReportFromRow);
}

export async function createShiftReport(
  workOrderId: string,
  expectedRevision: number,
  draft: ShiftReportDraft,
  actor: Actor,
) {
  const current = await getWorkOrder(workOrderId);
  if (!current) throw new FactoryRepositoryError("Work order not found.", 404);
  if (current.revision !== expectedRevision) {
    throw new FactoryRepositoryError(
      "This order changed since the shift began. Refresh before filing the report.",
      409,
    );
  }
  if (!(["CLAIMED", "IN_PROGRESS", "BLOCKED"] as const).includes(
    current.status as "CLAIMED" | "IN_PROGRESS" | "BLOCKED",
  )) {
    throw new FactoryRepositoryError(
      "Shift reports attach only to claimed, in-progress or blocked orders.",
      409,
    );
  }
  if (!current.assigneeUserId || current.assigneeUserId !== actor.userId) {
    throw new FactoryRepositoryError(
      "Only the operator who owns this order can file its shift report.",
      403,
    );
  }

  const database = getD1();
  const previous = await database
    .prepare(
      `SELECT report_sequence, report_sha256 FROM shift_reports
       WHERE work_order_id = ?
       ORDER BY report_sequence DESC
       LIMIT 1`,
    )
    .bind(workOrderId)
    .first<{ report_sequence: number; report_sha256: string }>();
  const reportSequence = (previous?.report_sequence ?? 0) + 1;
  const previousReportSha256 = previous?.report_sha256 ?? null;
  const reportId = makeId("SR");
  const createdAt = new Date().toISOString();
  const workOrderStatus = current.status as "CLAIMED" | "IN_PROGRESS" | "BLOCKED";
  const unsigned: Omit<ShiftReport, "reportSha256"> = {
    schemaVersion: 1,
    reportId,
    workOrderId,
    reportSequence,
    previousReportSha256,
    workbenchId: current.workbenchId,
    mode: current.mode,
    workOrderSnapshot: {
      status: workOrderStatus,
      revision: current.revision,
    },
    outcomeClass: draft.outcomeClass,
    shift: {
      startedAt: draft.startedAt,
      endedAt: draft.endedAt,
      durationMinutes: draft.durationMinutes,
    },
    attemptedWork: draft.attemptedWork,
    observations: draft.observations,
    artifactReferences: draft.artifactReferences,
    blockers: draft.blockers,
    nextLeads: draft.nextLeads,
    reporter: {
      actorUserId: actor.userId,
      actorDisplay: actor.displayName,
      identityAssurance: actor.assurance,
    },
    boundary: {
      scope: "HANGAR_OPERATIONS_ONLY",
      scientificEvidence: false,
      countsAsIndependentReproduction: false,
      eligibleForPromotion: false,
      closesWorkOrder: false,
      operationalRecordOnly: true,
    },
    createdAt,
  };
  const report: ShiftReport = {
    ...unsigned,
    reportSha256: await sha256Canonical(unsigned),
  };

  const statement = database
    .prepare(
      `INSERT INTO shift_reports (
        report_id, work_order_id, report_sequence, previous_report_sha256,
        report_sha256, workbench_id, mode, work_order_revision,
        work_order_status, outcome_class, report_json, actor_user_id,
        actor_display, created_at
      )
      SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
      FROM work_orders
      WHERE id = ? AND revision = ? AND assignee_user_id = ?
        AND status IN ('CLAIMED', 'IN_PROGRESS', 'BLOCKED')`,
    )
    .bind(
      report.reportId,
      report.workOrderId,
      report.reportSequence,
      report.previousReportSha256,
      report.reportSha256,
      report.workbenchId,
      report.mode,
      report.workOrderSnapshot.revision,
      report.workOrderSnapshot.status,
      report.outcomeClass,
      canonicalJson(report),
      actor.userId,
      actor.displayName,
      createdAt,
      workOrderId,
      expectedRevision,
      actor.userId,
    );

  let result: D1Result<unknown>;
  try {
    result = await statement.run();
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (/shift_reports|unique|constraint|sequence|previous hash/i.test(message)) {
      throw new FactoryRepositoryError(
        "Another shift report was filed concurrently. Refresh and submit a new report.",
        409,
      );
    }
    throw error;
  }
  if ((result.meta.changes ?? 0) !== 1) {
    throw new FactoryRepositoryError(
      "The work order changed before the report could be attached. Refresh and try again.",
      409,
    );
  }

  return report;
}

export async function listRunners() {
  await ensureHangarDatabase();
  const database = getD1();
  const result = await database
    .prepare("SELECT * FROM runner_profiles ORDER BY created_at DESC")
    .all<RunnerRow>();
  return result.results.map(runnerFromRow);
}

export async function createRunner(
  input: { label: string; trustClass: RunnerTrustClass; notes: string },
  actor: Actor,
) {
  await ensureHangarDatabase();
  const database = getD1();
  const id = makeId("RUN");
  const now = new Date().toISOString();
  await database.batch([
    database
      .prepare(
        `INSERT INTO runner_profiles (
          id, label, trust_class, status, notes, promotion_eligible,
          owner_user_id, owner_display, created_at, updated_at
        ) VALUES (?, ?, ?, 'REGISTERED', ?, 0, ?, ?, ?, ?)`,
      )
      .bind(
        id,
        input.label,
        input.trustClass,
        input.notes,
        actor.userId,
        actor.displayName,
        now,
        now,
      ),
    activityStatement(database, {
      eventType: "HANGAR_RUNNER_REGISTERED",
      entityType: "RUNNER",
      entityId: id,
      entityVersion: 0,
      mode: "HANGAR_CONSTRUCTION",
      actor,
      summary: `Registered commissioning runner ${id}`,
      payload: { label: input.label, trustClass: input.trustClass },
      createdAt: now,
    }),
  ]);

  const row = await database
    .prepare("SELECT * FROM runner_profiles WHERE id = ?")
    .bind(id)
    .first<RunnerRow>();
  if (!row) throw new FactoryRepositoryError("Runner registration failed.", 500);
  return runnerFromRow(row);
}

export async function listActivity(input?: {
  query?: string;
  mode?: OperatingMode;
  limit?: number;
}) {
  await ensureHangarDatabase();
  const database = getD1();
  const query = input?.query?.trim() ?? "";
  const mode = input?.mode ?? null;
  const limit = Math.min(Math.max(input?.limit ?? 100, 1), 250);
  const like = `%${query}%`;
  const result = await database
    .prepare(
      `SELECT * FROM activity_events
       WHERE (? = '' OR summary LIKE ? OR entity_id LIKE ? OR actor_display LIKE ? OR event_type LIKE ?)
         AND (? IS NULL OR mode = ?)
       ORDER BY sequence DESC
       LIMIT ?`,
    )
    .bind(query, like, like, like, like, mode, mode, limit)
    .all<ActivityRow>();
  return result.results.map(activityFromRow);
}
