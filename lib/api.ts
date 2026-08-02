import { FactoryAuthError } from "./auth";
import { FactoryRepositoryError } from "@/db/repository";

export const nonScientificBoundary = {
  scope: "HANGAR_OPERATIONS_ONLY",
  allowedModes: ["HANGAR_CONSTRUCTION", "SYNTHETIC_COMMISSIONING"],
  scientificEvidence: false,
  countsAsIndependentReproduction: false,
  eligibleForPromotion: false,
} as const;

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function assertExactKeys(
  value: Record<string, unknown>,
  allowed: readonly string[],
) {
  const extra = Object.keys(value).filter((key) => !allowed.includes(key));
  if (extra.length) {
    throw new ApiInputError(`Unsupported field${extra.length > 1 ? "s" : ""}: ${extra.join(", ")}.`);
  }
}

export function requiredString(
  value: unknown,
  label: string,
  min: number,
  max: number,
) {
  if (typeof value !== "string") {
    throw new ApiInputError(`${label} must be text.`);
  }
  const normalized = value.trim();
  if (normalized.length < min || normalized.length > max) {
    throw new ApiInputError(`${label} must be between ${min} and ${max} characters.`);
  }
  return normalized;
}

export function optionalString(value: unknown, label: string, max: number) {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value !== "string") {
    throw new ApiInputError(`${label} must be text.`);
  }
  const normalized = value.trim();
  if (normalized.length > max) {
    throw new ApiInputError(`${label} must be no longer than ${max} characters.`);
  }
  return normalized;
}

export class ApiInputError extends Error {
  constructor(
    message: string,
    public status = 400,
  ) {
    super(message);
  }
}

export function apiError(error: unknown) {
  if (error instanceof FactoryAuthError) {
    return Response.json({ error: error.message, boundary: nonScientificBoundary }, { status: 401 });
  }
  if (error instanceof FactoryRepositoryError || error instanceof ApiInputError) {
    return Response.json(
      { error: error.message, boundary: nonScientificBoundary },
      { status: error.status },
    );
  }
  const message = error instanceof Error ? error.message : "Unexpected error";
  const unavailable = /D1 binding|no such table|database/i.test(message);
  return Response.json(
    {
      error: unavailable
        ? "The hangar database is not available yet."
        : "The operation could not be completed.",
      boundary: nonScientificBoundary,
    },
    { status: unavailable ? 503 : 500 },
  );
}
