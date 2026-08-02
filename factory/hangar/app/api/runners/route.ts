import { createRunner, listRunners } from "@/db/repository";
import {
  ApiInputError,
  apiError,
  assertExactKeys,
  isPlainObject,
  nonScientificBoundary,
  optionalString,
  requiredString,
} from "@/lib/api";
import { requireActor } from "@/lib/auth";
import { isRunnerTrustClass } from "@/lib/factory-types";

export async function GET() {
  try {
    return Response.json({ runners: await listRunners(), boundary: nonScientificBoundary });
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request) {
  try {
    const actor = requireActor(request);
    const payload: unknown = await request.json();
    if (!isPlainObject(payload)) throw new ApiInputError("A JSON object is required.");
    assertExactKeys(payload, ["label", "trustClass", "notes"]);
    if (!isRunnerTrustClass(payload.trustClass)) {
      throw new ApiInputError(
        "Only trusted-code local runners and non-promotion container commissioning runners can be registered.",
        422,
      );
    }
    const runner = await createRunner(
      {
        label: requiredString(payload.label, "label", 3, 100),
        trustClass: payload.trustClass,
        notes: optionalString(payload.notes, "notes", 800),
      },
      actor,
    );
    return Response.json({ runner, boundary: nonScientificBoundary }, { status: 201 });
  } catch (error) {
    return apiError(error);
  }
}
