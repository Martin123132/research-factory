import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const expectedSha256 = "9b37a47c265e916cbf460f4dd0120b02b01fa800b104017b117ba2fc40644cd5";
const requiredFields = [
  "id",
  "category",
  "short_category",
  "evidence_lane",
  "workbench",
  "hard_gate_and_score",
  "economic_or_physical_guardrail",
  "benchmark",
  "reference_url",
  "starter_pack",
  "track",
];

const bytes = await readFile(new URL("../data/workbenches.json", import.meta.url));
const sha256 = createHash("sha256").update(bytes).digest("hex");
if (sha256 !== expectedSha256) {
  throw new Error(`Catalogue digest mismatch: expected ${expectedSha256}, received ${sha256}`);
}

const catalogue = JSON.parse(bytes.toString("utf8"));
if (catalogue.version !== 1) throw new Error("Catalogue version must be 1.");
if (catalogue.workbenches?.length !== 100) throw new Error("Catalogue must contain exactly 100 stations.");

const ids = catalogue.workbenches.map((item) => item.id);
if (new Set(ids).size !== 100 || ids.some((id, index) => id !== index + 1)) {
  throw new Error("Catalogue IDs must be unique and contiguous from 1 through 100.");
}

for (const item of catalogue.workbenches) {
  for (const field of requiredFields) {
    if (typeof item[field] === "string" ? !item[field].trim() : item[field] === undefined) {
      throw new Error(`WB-${String(item.id).padStart(3, "0")} is missing ${field}.`);
    }
  }
}

const categories = new Set(catalogue.workbenches.map((item) => item.short_category));
if (categories.size !== 9) throw new Error(`Expected 9 categories, received ${categories.size}.`);

console.log(`Catalogue verified: 100 stations, 9 categories, SHA-256 ${sha256}`);
