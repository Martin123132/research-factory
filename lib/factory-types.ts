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
