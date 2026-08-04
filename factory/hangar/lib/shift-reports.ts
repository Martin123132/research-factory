import {
  ApiInputError,
  assertExactKeys,
  isPlainObject,
  requiredString,
} from "./api";
import {
  isShiftArtifactKind,
  isShiftAttemptDecision,
  isShiftBlockerCategory,
  isShiftReportOutcome,
} from "./factory-types";
import type {
  ShiftArtifactReference,
  ShiftAttempt,
  ShiftBlocker,
  ShiftNextLead,
  ShiftReportDraft,
} from "./factory-types";

const SHA256 = /^[0-9a-f]{64}$/;
const UTC_TIMESTAMP =
  /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$/;
const MEDIA_TYPE = /^[a-z0-9.+-]+\/[a-zA-Z0-9.+-]+$/;
const FORBIDDEN_REPOSITORY_SEGMENT =
  /(^|\/)(?:private|secrets?|credentials?|keys?|hidden|hidden-answers?|holdouts?)(?:\/|$)|(^|\/)\.env(?:\.|$)/i;

function boundedArray(value: unknown, label: string, maximum: number, minimum = 0) {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) {
    throw new ApiInputError(
      `${label} must contain between ${minimum} and ${maximum} items.`,
    );
  }
  return value;
}

function utcTimestamp(value: unknown, label: string) {
  if (typeof value !== "string" || !UTC_TIMESTAMP.test(value)) {
    throw new ApiInputError(`${label} must be a UTC timestamp ending in Z.`);
  }
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) {
    throw new ApiInputError(`${label} is not a real UTC timestamp.`);
  }
  return new Date(milliseconds).toISOString();
}

function stringArray(value: unknown, label: string) {
  return boundedArray(value, label, 20).map((item, index) =>
    requiredString(item, `${label}[${index}]`, 1, 500),
  );
}

function parseAttempt(value: unknown, index: number): ShiftAttempt {
  if (!isPlainObject(value)) {
    throw new ApiInputError(`attemptedWork[${index}] must be an object.`);
  }
  assertExactKeys(value, ["approach", "result", "decision"]);
  if (!isShiftAttemptDecision(value.decision)) {
    throw new ApiInputError(`attemptedWork[${index}].decision is not supported.`);
  }
  return {
    approach: requiredString(value.approach, `attemptedWork[${index}].approach`, 3, 500),
    result: requiredString(value.result, `attemptedWork[${index}].result`, 1, 500),
    decision: value.decision,
  };
}

function safeRepositoryLocator(value: string) {
  if (
    value.startsWith("/") ||
    /^[A-Za-z]:/.test(value) ||
    value.includes("\\") ||
    value.includes("\r") ||
    value.includes("\n") ||
    value.includes("//") ||
    value.endsWith("/") ||
    value.split("/").some((part) => part === "." || part === "..") ||
    FORBIDDEN_REPOSITORY_SEGMENT.test(value)
  ) {
    throw new ApiInputError(
      "Repository artifact locators must be canonical public paths without private or evaluator material.",
    );
  }
  return value;
}

function safePublicUrl(value: string) {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new ApiInputError("Public artifact locators must be valid HTTPS URLs.");
  }
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.hostname === "localhost" ||
    parsed.hostname.endsWith(".local")
  ) {
    throw new ApiInputError("Public artifact locators must be credential-free HTTPS URLs.");
  }
  return parsed.toString();
}

function parseArtifact(value: unknown, index: number): ShiftArtifactReference {
  if (!isPlainObject(value)) {
    throw new ApiInputError(`artifactReferences[${index}] must be an object.`);
  }
  assertExactKeys(value, ["kind", "locator", "sha256", "mediaType", "purpose"]);
  if (!isShiftArtifactKind(value.kind)) {
    throw new ApiInputError(`artifactReferences[${index}].kind is not supported.`);
  }
  const locator = requiredString(value.locator, `artifactReferences[${index}].locator`, 1, 1000);
  const digest = requiredString(value.sha256, `artifactReferences[${index}].sha256`, 64, 64);
  if (!SHA256.test(digest)) {
    throw new ApiInputError(`artifactReferences[${index}].sha256 must be lowercase SHA-256.`);
  }
  const mediaType = requiredString(
    value.mediaType,
    `artifactReferences[${index}].mediaType`,
    3,
    100,
  );
  if (!MEDIA_TYPE.test(mediaType)) {
    throw new ApiInputError(`artifactReferences[${index}].mediaType is not valid.`);
  }
  return {
    kind: value.kind,
    locator:
      value.kind === "REPOSITORY_PATH"
        ? safeRepositoryLocator(locator)
        : safePublicUrl(locator),
    sha256: digest,
    mediaType,
    purpose: requiredString(value.purpose, `artifactReferences[${index}].purpose`, 3, 300),
    visibility: "PUBLIC",
    provenanceOnly: true,
  };
}

function parseBlocker(value: unknown, index: number): ShiftBlocker {
  if (!isPlainObject(value)) {
    throw new ApiInputError(`blockers[${index}] must be an object.`);
  }
  assertExactKeys(value, ["category", "description", "retryCondition"]);
  if (!isShiftBlockerCategory(value.category)) {
    throw new ApiInputError(`blockers[${index}].category is not supported.`);
  }
  return {
    category: value.category,
    description: requiredString(value.description, `blockers[${index}].description`, 1, 500),
    retryCondition: requiredString(
      value.retryCondition,
      `blockers[${index}].retryCondition`,
      1,
      500,
    ),
  };
}

function parseNextLead(value: unknown, index: number): ShiftNextLead {
  if (!isPlainObject(value)) {
    throw new ApiInputError(`nextLeads[${index}] must be an object.`);
  }
  assertExactKeys(value, ["lead", "rationale"]);
  return {
    lead: requiredString(value.lead, `nextLeads[${index}].lead`, 1, 500),
    rationale: requiredString(value.rationale, `nextLeads[${index}].rationale`, 1, 500),
  };
}

export function parseShiftReportDraft(payload: Record<string, unknown>): ShiftReportDraft {
  assertExactKeys(payload, [
    "expectedRevision",
    "outcomeClass",
    "startedAt",
    "endedAt",
    "attemptedWork",
    "observations",
    "artifactReferences",
    "blockers",
    "nextLeads",
  ]);
  if (!isShiftReportOutcome(payload.outcomeClass)) {
    throw new ApiInputError("outcomeClass must be PROGRESS, NO_GAIN, BLOCKED or UNRUNNABLE.");
  }
  const startedAt = utcTimestamp(payload.startedAt, "startedAt");
  const endedAt = utcTimestamp(payload.endedAt, "endedAt");
  const elapsed = Date.parse(endedAt) - Date.parse(startedAt);
  if (elapsed < 0 || elapsed > 24 * 60 * 60 * 1000) {
    throw new ApiInputError("A shift must end after it starts and cannot exceed 24 hours.");
  }
  const attemptedWork = boundedArray(payload.attemptedWork, "attemptedWork", 20, 1).map(
    parseAttempt,
  );
  const observations = stringArray(payload.observations, "observations");
  const artifactReferences = boundedArray(
    payload.artifactReferences,
    "artifactReferences",
    20,
  ).map(parseArtifact);
  const blockers = boundedArray(payload.blockers, "blockers", 10).map(parseBlocker);
  const nextLeads = boundedArray(payload.nextLeads, "nextLeads", 10).map(parseNextLead);

  if (
    (payload.outcomeClass === "PROGRESS" || payload.outcomeClass === "NO_GAIN") &&
    observations.length === 0
  ) {
    throw new ApiInputError(`${payload.outcomeClass} reports require at least one observation.`);
  }
  if (
    (payload.outcomeClass === "BLOCKED" || payload.outcomeClass === "UNRUNNABLE") &&
    blockers.length === 0
  ) {
    throw new ApiInputError(`${payload.outcomeClass} reports require at least one blocker.`);
  }

  return {
    outcomeClass: payload.outcomeClass,
    startedAt,
    endedAt,
    durationMinutes: Math.ceil(elapsed / 60000),
    attemptedWork,
    observations,
    artifactReferences,
    blockers,
    nextLeads,
  };
}
