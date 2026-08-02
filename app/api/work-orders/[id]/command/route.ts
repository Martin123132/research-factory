import { commandWorkOrder } from "@/db/repository";
import {
  ApiInputError,
  apiError,
  assertExactKeys,
  isPlainObject,
  nonScientificBoundary,
  optionalString,
} from "@/lib/api";
import { requireActor } from "@/lib/auth";
import { isWorkOrderCommand } from "@/lib/factory-types";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const actor = requireActor(request);
    const payload: unknown = await request.json();
    if (!isPlainObject(payload)) throw new ApiInputError("A JSON object is required.");
    assertExactKeys(payload, ["command", "expectedRevision", "note"]);
    if (!isWorkOrderCommand(payload.command)) {
      throw new ApiInputError("Unknown work-order command.");
    }
    if (!Number.isInteger(payload.expectedRevision) || (payload.expectedRevision as number) < 0) {
      throw new ApiInputError("expectedRevision must be a non-negative integer.");
    }
    const { id } = await context.params;
    const workOrder = await commandWorkOrder(
      id,
      payload.command,
      payload.expectedRevision as number,
      optionalString(payload.note, "note", 600),
      actor,
    );
    return Response.json({ workOrder, boundary: nonScientificBoundary });
  } catch (error) {
    return apiError(error);
  }
}
