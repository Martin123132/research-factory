import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const originalHash = "e572166565f15fa6ad9865ae49d678218e32aabfd1b3720f6d0d43d39800d310";
const anchor = "  const push = node => {\n";
const guard = "    // Research Factory local mitigation for GHSA-vfj7-8cjw-p6xm.\n"
  + "    if (node.nodes && stack.length > 100) {\n"
  + "      throw new SyntaxError('Research Factory: brace/parenthesis nesting exceeds 100');\n"
  + "    }\n\n";
const hash = (source) => createHash("sha256").update(source).digest("hex");

// Only transform the exact published 3.0.3 parser, never an unknown revision.
// Keep its name, version and MIT licence intact: npm audit must still report it.
export function guardedSource(source, checkOnly = false) {
  if (source.includes(guard) && hash(source.replace(guard, "")) === originalHash) {
    return source;
  }
  if (hash(source) !== originalHash) throw new Error("Unrecognised braces parser; manual review required");
  if (checkOnly) throw new Error("Missing braces depth guard; run npm run postinstall");
  return source.replace(anchor, anchor + guard);
}

export function verifyOrInstallGuards({ checkOnly = true, root = projectRoot } = {}) {
  const lock = JSON.parse(readFileSync(resolve(root, "package-lock.json"), "utf8"));
  const entries = Object.entries(lock.packages).filter(([path]) => /(^|\/)node_modules\/braces$/.test(path));
  if (entries.length === 0) throw new Error("braces dependency changed; retire/review the mitigation");
  const installed = [];
  for (const [path, info] of entries) {
    if (info.version !== "3.0.3" || info.dev !== true) {
      throw new Error(`Unexpected braces version or production exposure: ${path}`);
    }
    const manifest = resolve(root, path, "package.json");
    // npm ci --omit=dev legitimately has no braces. The full audit requires it.
    if (!existsSync(manifest) && !checkOnly) continue;
    const pkg = JSON.parse(readFileSync(manifest, "utf8"));
    if (pkg.name !== "braces" || pkg.version !== info.version) throw new Error(`Unexpected installed package: ${path}`);
    const file = resolve(dirname(manifest), "lib/parse.js");
    const source = readFileSync(file, "utf8");
    const patched = guardedSource(source, checkOnly);
    if (patched !== source) writeFileSync(file, patched);
    installed.push(path);
  }
  return installed;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const installed = verifyOrInstallGuards({ checkOnly: process.argv.includes("--check") });
  console.log(`braces local depth guard: ${installed.length} installed copy/copies verified (upstream advisory remains open)`);
}
