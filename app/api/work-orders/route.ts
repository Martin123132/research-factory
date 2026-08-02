import { createWorkOrder, listWorkOrders } from "@/db/repository";
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
import { isOperatingMode } from "@/lib/factory-types";
import { getWorkbench } from "@/lib/workbenches";

export async function GET() {
  try {
    return Response.json({ workOrders: await listWorkOrders(), boundary: nonScientificBoundary });
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(request: Request) {
  try {
    const actor = requireActor(request);
    const payload: unknown = await request.json();
    if (!isPlainObject(payload)) throw new ApiInputError("A JSON object is required.");
    assertExactKeys(payload, ["workbenchId", "mode", "title", "description"]);

    if (!Number.isInteger(payload.workbenchId) || !getWorkbench(payload.workbenchId as number)) {
      throw new ApiInputError("workbenchId must identify one of the 100 catalogue stations.");
    }
    if (!isOperatingMode(payload.mode)) {
      throw new ApiInputError(
        "mode must be HANGAR_CONSTRUCTION or SYNTHETIC_COMMISSIONING. Live research is not available here.",
        422,
      );
    }
    if (actor.assurance === "LOCAL_PREVIEW" && payload.mode !== "SYNTHETIC_COMMISSIONING") {
      throw new ApiInputError(
        "Local preview identities may create synthetic commissioning orders only.",
        403,
      );
    }

    const workOrder = await createWorkOrder(
      {
        workbenchId: payload.workbenchId as number,
        mode: payload.mode,
        title: requiredString(payload.title, "title", 4, 120),
        description: optionalString(payload.description, "description", 1200),
      },
      actor,
    );
    return Response.json({ workOrder, boundary: nonScientificBoundary }, { status: 201 });
  } catch (error) {
    return apiError(error);
  }
}
