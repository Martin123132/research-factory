import {
  createShiftReport,
  FactoryRepositoryError,
  getWorkOrder,
  listShiftReports,
} from "@/db/repository";
import {
  ApiInputError,
  apiError,
  isPlainObject,
  nonScientificBoundary,
} from "@/lib/api";
import { requireActor } from "@/lib/auth";
import { parseShiftReportDraft } from "@/lib/shift-reports";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await context.params;
    if (!(await getWorkOrder(id))) {
      throw new FactoryRepositoryError("Work order not found.", 404);
    }
    const shiftReports = await listShiftReports(id);
    return Response.json({ shiftReports, boundary: nonScientificBoundary });
  } catch (error) {
    return apiError(error);
  }
}

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const actor = requireActor(request);
    const payload: unknown = await request.json();
    if (!isPlainObject(payload)) throw new ApiInputError("A JSON object is required.");
    if (!Number.isInteger(payload.expectedRevision) || (payload.expectedRevision as number) < 0) {
      throw new ApiInputError("expectedRevision must be a non-negative integer.");
    }
    const draft = parseShiftReportDraft(payload);
    const { id } = await context.params;
    const shiftReport = await createShiftReport(
      id,
      payload.expectedRevision as number,
      draft,
      actor,
    );
    return Response.json(
      { shiftReport, boundary: nonScientificBoundary },
      { status: 201 },
    );
  } catch (error) {
    return apiError(error);
  }
}
