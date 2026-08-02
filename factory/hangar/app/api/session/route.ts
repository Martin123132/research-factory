import { actorFromRequest } from "@/lib/auth";
import { nonScientificBoundary } from "@/lib/api";

export async function GET(request: Request) {
  return Response.json({ actor: actorFromRequest(request), boundary: nonScientificBoundary });
}
