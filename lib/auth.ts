import type { Actor } from "./factory-types";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function decodeName(value: string | null, encoding: string | null) {
  if (!value || encoding !== "percent-encoded-utf-8") return null;
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

export function actorFromRequest(request: Request): Actor | null {
  const userId = request.headers.get("oai-authenticated-user-id");
  const email = request.headers.get("oai-authenticated-user-email");

  if (userId && email) {
    const fullName = decodeName(
      request.headers.get("oai-authenticated-user-full-name"),
      request.headers.get("oai-authenticated-user-full-name-encoding"),
    );
    return {
      userId,
      email,
      displayName: fullName ?? email,
      assurance: "PLATFORM_HEADER",
    };
  }

  const hostname = new URL(request.url).hostname;
  if (LOCAL_HOSTS.has(hostname)) {
    return {
      userId: "local-preview-operator",
      email: "local-preview@factory.invalid",
      displayName: "Local commissioning operator",
      assurance: "LOCAL_PREVIEW",
    };
  }

  return null;
}

export function requireActor(request: Request): Actor {
  const actor = actorFromRequest(request);
  if (!actor) {
    throw new FactoryAuthError(
      "A platform-authenticated operator is required for this write.",
    );
  }
  return actor;
}

export class FactoryAuthError extends Error {}
