import { listActivity } from "@/db/repository";
import { ApiInputError, apiError, nonScientificBoundary } from "@/lib/api";
import { isOperatingMode } from "@/lib/factory-types";
import type { OperatingMode } from "@/lib/factory-types";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const query = (url.searchParams.get("q") ?? "").trim().slice(0, 120);
    const requestedMode = url.searchParams.get("mode");
    let mode: OperatingMode | undefined;
    if (requestedMode && !isOperatingMode(requestedMode)) {
      throw new ApiInputError("Unknown operating mode.");
    }
    if (requestedMode && isOperatingMode(requestedMode)) mode = requestedMode;
    const activity = await listActivity({
      query,
      mode,
      limit: 200,
    });
    return Response.json({ activity, boundary: nonScientificBoundary });
  } catch (error) {
    return apiError(error);
  }
}
