import { sql } from "drizzle-orm";
import {
  check,
  index,
  integer,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const schemaMetadata = sqliteTable("schema_metadata", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});

export const workOrders = sqliteTable(
  "work_orders",
  {
    id: text("id").primaryKey(),
    workbenchId: integer("workbench_id").notNull(),
    mode: text("mode").notNull(),
    title: text("title").notNull(),
    description: text("description").notNull().default(""),
    status: text("status").notNull().default("OPEN"),
    assigneeUserId: text("assignee_user_id"),
    assigneeDisplay: text("assignee_display"),
    createdByUserId: text("created_by_user_id").notNull(),
    createdByDisplay: text("created_by_display").notNull(),
    blockedReason: text("blocked_reason"),
    scientificEvidence: integer("scientific_evidence", { mode: "boolean" })
      .notNull()
      .default(false),
    countsAsIndependentReproduction: integer(
      "counts_as_independent_reproduction",
      { mode: "boolean" },
    )
      .notNull()
      .default(false),
    eligibleForPromotion: integer("eligible_for_promotion", { mode: "boolean" })
      .notNull()
      .default(false),
    revision: integer("revision").notNull().default(0),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    completedAt: text("completed_at"),
  },
  (table) => [
    check("work_orders_workbench_check", sql`${table.workbenchId} BETWEEN 1 AND 100`),
    check(
      "work_orders_mode_check",
      sql`${table.mode} IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')`,
    ),
    check(
      "work_orders_status_check",
      sql`${table.status} IN ('OPEN', 'CLAIMED', 'IN_PROGRESS', 'BLOCKED', 'REVIEW', 'COMPLETED')`,
    ),
    check("work_orders_no_evidence_check", sql`${table.scientificEvidence} = 0`),
    check(
      "work_orders_no_reproduction_check",
      sql`${table.countsAsIndependentReproduction} = 0`,
    ),
    check("work_orders_no_promotion_check", sql`${table.eligibleForPromotion} = 0`),
    index("work_orders_status_idx").on(table.status),
    index("work_orders_workbench_idx").on(table.workbenchId),
    index("work_orders_mode_idx").on(table.mode),
  ],
);

export const shiftReports = sqliteTable(
  "shift_reports",
  {
    sequence: integer("sequence").primaryKey({ autoIncrement: true }),
    reportId: text("report_id").notNull().unique(),
    workOrderId: text("work_order_id")
      .notNull()
      .references(() => workOrders.id, { onDelete: "restrict" }),
    reportSequence: integer("report_sequence").notNull(),
    previousReportSha256: text("previous_report_sha256"),
    reportSha256: text("report_sha256").notNull().unique(),
    workbenchId: integer("workbench_id").notNull(),
    mode: text("mode").notNull(),
    workOrderRevision: integer("work_order_revision").notNull(),
    workOrderStatus: text("work_order_status").notNull(),
    outcomeClass: text("outcome_class").notNull(),
    reportJson: text("report_json").notNull(),
    actorUserId: text("actor_user_id").notNull(),
    actorDisplay: text("actor_display").notNull(),
    scientificEvidence: integer("scientific_evidence", { mode: "boolean" })
      .notNull()
      .default(false),
    countsAsIndependentReproduction: integer(
      "counts_as_independent_reproduction",
      { mode: "boolean" },
    )
      .notNull()
      .default(false),
    eligibleForPromotion: integer("eligible_for_promotion", { mode: "boolean" })
      .notNull()
      .default(false),
    closesWorkOrder: integer("closes_work_order", { mode: "boolean" })
      .notNull()
      .default(false),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    check("shift_reports_sequence_check", sql`${table.reportSequence} >= 1`),
    check("shift_reports_workbench_check", sql`${table.workbenchId} BETWEEN 1 AND 100`),
    check(
      "shift_reports_mode_check",
      sql`${table.mode} IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')`,
    ),
    check(
      "shift_reports_status_check",
      sql`${table.workOrderStatus} IN ('CLAIMED', 'IN_PROGRESS', 'BLOCKED')`,
    ),
    check(
      "shift_reports_outcome_check",
      sql`${table.outcomeClass} IN ('PROGRESS', 'NO_GAIN', 'BLOCKED', 'UNRUNNABLE')`,
    ),
    check(
      "shift_reports_chain_check",
      sql`((${table.reportSequence} = 1 AND ${table.previousReportSha256} IS NULL) OR (${table.reportSequence} > 1 AND ${table.previousReportSha256} IS NOT NULL))`,
    ),
    check("shift_reports_no_evidence_check", sql`${table.scientificEvidence} = 0`),
    check(
      "shift_reports_no_reproduction_check",
      sql`${table.countsAsIndependentReproduction} = 0`,
    ),
    check("shift_reports_no_promotion_check", sql`${table.eligibleForPromotion} = 0`),
    check("shift_reports_no_completion_check", sql`${table.closesWorkOrder} = 0`),
    uniqueIndex("shift_reports_work_order_sequence_idx").on(
      table.workOrderId,
      table.reportSequence,
    ),
    index("shift_reports_work_order_idx").on(table.workOrderId),
    index("shift_reports_outcome_idx").on(table.outcomeClass),
    index("shift_reports_created_idx").on(table.createdAt),
  ],
);

export const runnerProfiles = sqliteTable(
  "runner_profiles",
  {
    id: text("id").primaryKey(),
    label: text("label").notNull(),
    trustClass: text("trust_class").notNull(),
    status: text("status").notNull().default("REGISTERED"),
    notes: text("notes").notNull().default(""),
    promotionEligible: integer("promotion_eligible", { mode: "boolean" })
      .notNull()
      .default(false),
    ownerUserId: text("owner_user_id").notNull(),
    ownerDisplay: text("owner_display").notNull(),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    check(
      "runner_profiles_trust_check",
      sql`${table.trustClass} IN ('LOCAL_TRUSTED_CODE_ONLY', 'CONTAINER_COMMISSIONING_ONLY')`,
    ),
    check("runner_profiles_status_check", sql`${table.status} = 'REGISTERED'`),
    check("runner_profiles_no_promotion_check", sql`${table.promotionEligible} = 0`),
    index("runner_profiles_status_idx").on(table.status),
    index("runner_profiles_owner_idx").on(table.ownerUserId),
  ],
);

export const activityEvents = sqliteTable(
  "activity_events",
  {
    sequence: integer("sequence").primaryKey({ autoIncrement: true }),
    eventId: text("event_id").notNull().unique(),
    eventType: text("event_type").notNull(),
    entityType: text("entity_type").notNull(),
    entityId: text("entity_id").notNull(),
    entityVersion: integer("entity_version").notNull(),
    mode: text("mode").notNull(),
    actorUserId: text("actor_user_id").notNull(),
    actorDisplay: text("actor_display").notNull(),
    summary: text("summary").notNull(),
    payloadJson: text("payload_json").notNull().default("{}"),
    scientificEvidence: integer("scientific_evidence", { mode: "boolean" })
      .notNull()
      .default(false),
    countsAsIndependentReproduction: integer(
      "counts_as_independent_reproduction",
      { mode: "boolean" },
    )
      .notNull()
      .default(false),
    eligibleForPromotion: integer("eligible_for_promotion", { mode: "boolean" })
      .notNull()
      .default(false),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => [
    check(
      "activity_events_type_check",
      sql`${table.eventType} IN ('HANGAR_WORK_ORDER_CREATED', 'HANGAR_WORK_ORDER_STATE_CHANGED', 'HANGAR_RUNNER_REGISTERED')`,
    ),
    check(
      "activity_events_entity_check",
      sql`${table.entityType} IN ('WORK_ORDER', 'RUNNER')`,
    ),
    check(
      "activity_events_mode_check",
      sql`${table.mode} IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')`,
    ),
    check("activity_events_no_evidence_check", sql`${table.scientificEvidence} = 0`),
    check(
      "activity_events_no_reproduction_check",
      sql`${table.countsAsIndependentReproduction} = 0`,
    ),
    check("activity_events_no_promotion_check", sql`${table.eligibleForPromotion} = 0`),
    uniqueIndex("activity_events_entity_version_idx").on(
      table.entityType,
      table.entityId,
      table.entityVersion,
    ),
    index("activity_events_type_idx").on(table.eventType),
    index("activity_events_entity_idx").on(table.entityType, table.entityId),
    index("activity_events_mode_idx").on(table.mode),
    index("activity_events_created_idx").on(table.createdAt),
  ],
);
