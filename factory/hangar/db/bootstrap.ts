import { getD1 } from "./index";

const schemaStatements = [
  `CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS work_orders (
    id TEXT PRIMARY KEY NOT NULL,
    workbench_id INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLAIMED', 'IN_PROGRESS', 'BLOCKED', 'REVIEW', 'COMPLETED')),
    assignee_user_id TEXT,
    assignee_display TEXT,
    created_by_user_id TEXT NOT NULL,
    created_by_display TEXT NOT NULL,
    blocked_reason TEXT,
    scientific_evidence INTEGER NOT NULL DEFAULT 0 CHECK (scientific_evidence = 0),
    counts_as_independent_reproduction INTEGER NOT NULL DEFAULT 0 CHECK (counts_as_independent_reproduction = 0),
    eligible_for_promotion INTEGER NOT NULL DEFAULT 0 CHECK (eligible_for_promotion = 0),
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS shift_reports (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL UNIQUE,
    work_order_id TEXT NOT NULL REFERENCES work_orders(id) ON DELETE RESTRICT,
    report_sequence INTEGER NOT NULL CHECK (report_sequence >= 1),
    previous_report_sha256 TEXT,
    report_sha256 TEXT NOT NULL UNIQUE,
    workbench_id INTEGER NOT NULL CHECK (workbench_id BETWEEN 1 AND 100),
    mode TEXT NOT NULL CHECK (mode IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')),
    work_order_revision INTEGER NOT NULL,
    work_order_status TEXT NOT NULL CHECK (work_order_status IN ('CLAIMED', 'IN_PROGRESS', 'BLOCKED')),
    outcome_class TEXT NOT NULL CHECK (outcome_class IN ('PROGRESS', 'NO_GAIN', 'BLOCKED', 'UNRUNNABLE')),
    report_json TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    actor_display TEXT NOT NULL,
    scientific_evidence INTEGER NOT NULL DEFAULT 0 CHECK (scientific_evidence = 0),
    counts_as_independent_reproduction INTEGER NOT NULL DEFAULT 0 CHECK (counts_as_independent_reproduction = 0),
    eligible_for_promotion INTEGER NOT NULL DEFAULT 0 CHECK (eligible_for_promotion = 0),
    closes_work_order INTEGER NOT NULL DEFAULT 0 CHECK (closes_work_order = 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((report_sequence = 1 AND previous_report_sha256 IS NULL) OR (report_sequence > 1 AND previous_report_sha256 IS NOT NULL)),
    UNIQUE (work_order_id, report_sequence)
  )`,
  `CREATE TABLE IF NOT EXISTS runner_profiles (
    id TEXT PRIMARY KEY NOT NULL,
    label TEXT NOT NULL,
    trust_class TEXT NOT NULL CHECK (trust_class IN ('LOCAL_TRUSTED_CODE_ONLY', 'CONTAINER_COMMISSIONING_ONLY')),
    status TEXT NOT NULL DEFAULT 'REGISTERED' CHECK (status = 'REGISTERED'),
    notes TEXT NOT NULL DEFAULT '',
    promotion_eligible INTEGER NOT NULL DEFAULT 0 CHECK (promotion_eligible = 0),
    owner_user_id TEXT NOT NULL,
    owner_display TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  `CREATE TABLE IF NOT EXISTS activity_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK (event_type IN ('HANGAR_WORK_ORDER_CREATED', 'HANGAR_WORK_ORDER_STATE_CHANGED', 'HANGAR_RUNNER_REGISTERED')),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('WORK_ORDER', 'RUNNER')),
    entity_id TEXT NOT NULL,
    entity_version INTEGER NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('HANGAR_CONSTRUCTION', 'SYNTHETIC_COMMISSIONING')),
    actor_user_id TEXT NOT NULL,
    actor_display TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    scientific_evidence INTEGER NOT NULL DEFAULT 0 CHECK (scientific_evidence = 0),
    counts_as_independent_reproduction INTEGER NOT NULL DEFAULT 0 CHECK (counts_as_independent_reproduction = 0),
    eligible_for_promotion INTEGER NOT NULL DEFAULT 0 CHECK (eligible_for_promotion = 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )`,
  "CREATE INDEX IF NOT EXISTS work_orders_status_idx ON work_orders(status)",
  "CREATE INDEX IF NOT EXISTS work_orders_workbench_idx ON work_orders(workbench_id)",
  "CREATE INDEX IF NOT EXISTS work_orders_mode_idx ON work_orders(mode)",
  "CREATE INDEX IF NOT EXISTS shift_reports_work_order_idx ON shift_reports(work_order_id)",
  "CREATE INDEX IF NOT EXISTS shift_reports_outcome_idx ON shift_reports(outcome_class)",
  "CREATE INDEX IF NOT EXISTS shift_reports_created_idx ON shift_reports(created_at)",
  "CREATE INDEX IF NOT EXISTS runner_profiles_status_idx ON runner_profiles(status)",
  "CREATE INDEX IF NOT EXISTS runner_profiles_owner_idx ON runner_profiles(owner_user_id)",
  "CREATE INDEX IF NOT EXISTS activity_events_type_idx ON activity_events(event_type)",
  "CREATE INDEX IF NOT EXISTS activity_events_entity_idx ON activity_events(entity_type, entity_id)",
  "CREATE UNIQUE INDEX IF NOT EXISTS activity_events_entity_version_idx ON activity_events(entity_type, entity_id, entity_version)",
  "CREATE INDEX IF NOT EXISTS activity_events_mode_idx ON activity_events(mode)",
  "CREATE INDEX IF NOT EXISTS activity_events_created_idx ON activity_events(created_at)",
  `CREATE TRIGGER IF NOT EXISTS activity_events_reject_update
   BEFORE UPDATE ON activity_events
   BEGIN SELECT RAISE(ABORT, 'activity_events is append-only'); END`,
  `CREATE TRIGGER IF NOT EXISTS activity_events_reject_delete
   BEFORE DELETE ON activity_events
   BEGIN SELECT RAISE(ABORT, 'activity_events is append-only'); END`,
  `CREATE TRIGGER IF NOT EXISTS shift_reports_reject_update
   BEFORE UPDATE ON shift_reports
   BEGIN SELECT RAISE(ABORT, 'shift_reports is append-only'); END`,
  `CREATE TRIGGER IF NOT EXISTS shift_reports_reject_delete
   BEFORE DELETE ON shift_reports
   BEGIN SELECT RAISE(ABORT, 'shift_reports is append-only'); END`,
  `CREATE TRIGGER IF NOT EXISTS shift_reports_enforce_chain
   BEFORE INSERT ON shift_reports
   BEGIN
     SELECT CASE
       WHEN NEW.report_sequence != COALESCE((
         SELECT MAX(report_sequence) + 1 FROM shift_reports
         WHERE work_order_id = NEW.work_order_id
       ), 1)
       THEN RAISE(ABORT, 'shift_reports sequence must append')
     END;
     SELECT CASE
       WHEN NEW.previous_report_sha256 IS NOT (
         SELECT report_sha256 FROM shift_reports
         WHERE work_order_id = NEW.work_order_id
         ORDER BY report_sequence DESC LIMIT 1
       )
       THEN RAISE(ABORT, 'shift_reports previous hash must match the chain head')
     END;
   END`,
  `INSERT INTO schema_metadata (key, value, updated_at)
   VALUES ('hangar_schema_version', '2', CURRENT_TIMESTAMP)
   ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP`,
];

let bootstrapPromise: Promise<void> | null = null;

async function bootstrap() {
  const database = getD1();
  await database.batch(
    schemaStatements.map((statement) => database.prepare(statement)),
  );
}

export function ensureHangarDatabase() {
  if (!bootstrapPromise) {
    bootstrapPromise = bootstrap().catch((error) => {
      bootstrapPromise = null;
      throw error;
    });
  }
  return bootstrapPromise;
}
