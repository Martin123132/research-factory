export const OPERATING_MODES = [
  "HANGAR_CONSTRUCTION",
  "SYNTHETIC_COMMISSIONING",
] as const;

export type OperatingMode = (typeof OPERATING_MODES)[number];

export const WORK_ORDER_STATUSES = [
  "OPEN",
  "CLAIMED",
  "IN_PROGRESS",
  "BLOCKED",
  "REVIEW",
  "COMPLETED",
] as const;

export type WorkOrderStatus = (typeof WORK_ORDER_STATUSES)[number];

export const WORK_ORDER_COMMANDS = [
  "CLAIM",
  "START",
  "RELEASE",
  "BLOCK",
  "RESUME",
  "REQUEST_REVIEW",
  "RETURN_TO_WORK",
  "COMPLETE",
] as const;

export type WorkOrderCommand = (typeof WORK_ORDER_COMMANDS)[number];

export const RUNNER_TRUST_CLASSES = [
  "LOCAL_TRUSTED_CODE_ONLY",
  "CONTAINER_COMMISSIONING_ONLY",
] as const;

export type RunnerTrustClass = (typeof RUNNER_TRUST_CLASSES)[number];

export const SHIFT_REPORT_OUTCOMES = [
  "PROGRESS",
  "NO_GAIN",
  "BLOCKED",
  "UNRUNNABLE",
] as const;

export type ShiftReportOutcome = (typeof SHIFT_REPORT_OUTCOMES)[number];

export const SHIFT_ATTEMPT_DECISIONS = [
  "CONTINUE",
  "PAUSE",
  "ABANDON",
  "REVISIT_WITH_CONDITION",
] as const;

export type ShiftAttemptDecision = (typeof SHIFT_ATTEMPT_DECISIONS)[number];

export const SHIFT_BLOCKER_CATEGORIES = [
  "DEPENDENCY",
  "ENVIRONMENT",
  "RESOURCE",
  "SPECIFICATION",
  "ACCESS",
  "OTHER",
] as const;

export type ShiftBlockerCategory = (typeof SHIFT_BLOCKER_CATEGORIES)[number];

export const SHIFT_ARTIFACT_KINDS = ["REPOSITORY_PATH", "PUBLIC_URL"] as const;

export type ShiftArtifactKind = (typeof SHIFT_ARTIFACT_KINDS)[number];

export type IdentityAssurance = "PLATFORM_HEADER" | "LOCAL_PREVIEW";

export type Actor = {
  userId: string;
  email: string;
  displayName: string;
  assurance: IdentityAssurance;
};

export type WorkOrder = {
  id: string;
  workbenchId: number;
  mode: OperatingMode;
  title: string;
  description: string;
  status: WorkOrderStatus;
  assigneeUserId: string | null;
  assigneeDisplay: string | null;
  createdByUserId: string;
  createdByDisplay: string;
  blockedReason: string | null;
  scientificEvidence: false;
  countsAsIndependentReproduction: false;
  eligibleForPromotion: false;
  revision: number;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
};

export type RunnerProfile = {
  id: string;
  label: string;
  trustClass: RunnerTrustClass;
  status: "REGISTERED";
  notes: string;
  promotionEligible: false;
  ownerUserId: string;
  ownerDisplay: string;
  createdAt: string;
  updatedAt: string;
};

export type ActivityEvent = {
  sequence: number;
  eventId: string;
  eventType: string;
  entityType: "WORK_ORDER" | "RUNNER";
  entityId: string;
  entityVersion: number;
  mode: OperatingMode;
  actorUserId: string;
  actorDisplay: string;
  summary: string;
  payload: Record<string, unknown>;
  scientificEvidence: false;
  countsAsIndependentReproduction: false;
  eligibleForPromotion: false;
  createdAt: string;
};

export type ShiftAttempt = {
  approach: string;
  result: string;
  decision: ShiftAttemptDecision;
};

export type ShiftArtifactReference = {
  kind: ShiftArtifactKind;
  locator: string;
  sha256: string;
  mediaType: string;
  purpose: string;
  visibility: "PUBLIC";
  provenanceOnly: true;
};

export type ShiftBlocker = {
  category: ShiftBlockerCategory;
  description: string;
  retryCondition: string;
};

export type ShiftNextLead = {
  lead: string;
  rationale: string;
};

export type ShiftReportDraft = {
  outcomeClass: ShiftReportOutcome;
  startedAt: string;
  endedAt: string;
  durationMinutes: number;
  attemptedWork: ShiftAttempt[];
  observations: string[];
  artifactReferences: ShiftArtifactReference[];
  blockers: ShiftBlocker[];
  nextLeads: ShiftNextLead[];
};

export type ShiftReport = {
  schemaVersion: 1;
  reportId: string;
  workOrderId: string;
  reportSequence: number;
  previousReportSha256: string | null;
  reportSha256: string;
  workbenchId: number;
  mode: OperatingMode;
  workOrderSnapshot: {
    status: "CLAIMED" | "IN_PROGRESS" | "BLOCKED";
    revision: number;
  };
  outcomeClass: ShiftReportOutcome;
  shift: {
    startedAt: string;
    endedAt: string;
    durationMinutes: number;
  };
  attemptedWork: ShiftAttempt[];
  observations: string[];
  artifactReferences: ShiftArtifactReference[];
  blockers: ShiftBlocker[];
  nextLeads: ShiftNextLead[];
  reporter: {
    actorUserId: string;
    actorDisplay: string;
    identityAssurance: IdentityAssurance;
  };
  boundary: {
    scope: "HANGAR_OPERATIONS_ONLY";
    scientificEvidence: false;
    countsAsIndependentReproduction: false;
    eligibleForPromotion: false;
    closesWorkOrder: false;
    operationalRecordOnly: true;
  };
  createdAt: string;
};

export const STATUS_TRANSITIONS: Record<
  WorkOrderStatus,
  readonly WorkOrderStatus[]
> = {
  OPEN: ["CLAIMED"],
  CLAIMED: ["IN_PROGRESS", "OPEN"],
  IN_PROGRESS: ["REVIEW", "BLOCKED", "OPEN"],
  BLOCKED: ["IN_PROGRESS", "OPEN"],
  REVIEW: ["COMPLETED", "IN_PROGRESS"],
  COMPLETED: [],
};

const COMMAND_TRANSITIONS: Record<
  WorkOrderStatus,
  Partial<Record<WorkOrderCommand, WorkOrderStatus>>
> = {
  OPEN: { CLAIM: "CLAIMED" },
  CLAIMED: { START: "IN_PROGRESS", RELEASE: "OPEN" },
  IN_PROGRESS: {
    REQUEST_REVIEW: "REVIEW",
    BLOCK: "BLOCKED",
    RELEASE: "OPEN",
  },
  BLOCKED: { RESUME: "IN_PROGRESS", RELEASE: "OPEN" },
  REVIEW: { COMPLETE: "COMPLETED", RETURN_TO_WORK: "IN_PROGRESS" },
  COMPLETED: {},
};

export function nextStatusForCommand(
  status: WorkOrderStatus,
  command: WorkOrderCommand,
) {
  return COMMAND_TRANSITIONS[status][command] ?? null;
}

export function isOperatingMode(value: unknown): value is OperatingMode {
  return typeof value === "string" && OPERATING_MODES.includes(value as OperatingMode);
}

export function isWorkOrderStatus(value: unknown): value is WorkOrderStatus {
  return (
    typeof value === "string" &&
    WORK_ORDER_STATUSES.includes(value as WorkOrderStatus)
  );
}

export function isWorkOrderCommand(value: unknown): value is WorkOrderCommand {
  return (
    typeof value === "string" &&
    WORK_ORDER_COMMANDS.includes(value as WorkOrderCommand)
  );
}

export function isRunnerTrustClass(value: unknown): value is RunnerTrustClass {
  return (
    typeof value === "string" &&
    RUNNER_TRUST_CLASSES.includes(value as RunnerTrustClass)
  );
}

export function isShiftReportOutcome(value: unknown): value is ShiftReportOutcome {
  return (
    typeof value === "string" &&
    SHIFT_REPORT_OUTCOMES.includes(value as ShiftReportOutcome)
  );
}

export function isShiftAttemptDecision(value: unknown): value is ShiftAttemptDecision {
  return (
    typeof value === "string" &&
    SHIFT_ATTEMPT_DECISIONS.includes(value as ShiftAttemptDecision)
  );
}

export function isShiftBlockerCategory(value: unknown): value is ShiftBlockerCategory {
  return (
    typeof value === "string" &&
    SHIFT_BLOCKER_CATEGORIES.includes(value as ShiftBlockerCategory)
  );
}

export function isShiftArtifactKind(value: unknown): value is ShiftArtifactKind {
  return (
    typeof value === "string" &&
    SHIFT_ARTIFACT_KINDS.includes(value as ShiftArtifactKind)
  );
}
