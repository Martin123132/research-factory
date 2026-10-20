import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { verifyOrInstallGuards } from "./guard-braces.mjs";

const advisory = "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm";

// An explicit, narrow mitigation record, NOT a clean npm audit. Follow indirect
// advisory edges so a new advisory on any ancestor cannot pass this gate.
export function assessAudit(report, guardedPaths) {
  if (report.error || report.auditReportVersion !== 2 || !report.vulnerabilities
      || !report.metadata?.vulnerabilities) throw new Error("Invalid/incomplete npm audit response");
  const entries = report.vulnerabilities;
  if (report.metadata.vulnerabilities.total !== Object.keys(entries).length) {
    throw new Error("Inconsistent npm audit totals");
  }
  const mitigated = (name, visited = new Set()) => {
    if (visited.has(name)) return false;
    const item = entries[name];
    if (!item || !Array.isArray(item.via) || !item.via.length) return false;
    const next = new Set([...visited, name]);
    return item.via.every((cause) => {
      if (typeof cause === "string") return mitigated(cause, next);
      return name === "braces" && cause.name === "braces" && cause.url === advisory
        && cause.range === "<=3.0.3" && cause.severity === "high"
        && Array.isArray(item.nodes) && item.nodes.length > 0
        && item.nodes.every((path) => guardedPaths.includes(path));
    });
  };
  const unexpected = Object.keys(entries).filter((name) => !mitigated(name));
  if (unexpected.length) throw new Error(`Unmitigated dependency advisories: ${unexpected.join(", ")}`);
  return Object.keys(entries);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const paths = verifyOrInstallGuards();
  // npm supplies its actual CLI path to npm run, avoiding Windows shell quoting.
  if (!process.env.npm_execpath) throw new Error("Run this gate with npm run security:audit");
  const result = spawnSync(process.execPath, [process.env.npm_execpath, "audit", "--include=dev", "--json"], {
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    encoding: "utf8", timeout: 120_000, maxBuffer: 8 * 1024 * 1024,
  });
  if (result.error || ![0, 1].includes(result.status)) throw result.error ?? new Error(result.stderr || "npm audit failed");
  const report = JSON.parse(result.stdout);
  const names = assessAudit(report, paths);
  console.log(JSON.stringify(report.metadata.vulnerabilities));
  if (names.length) {
    console.log(`LOCALLY MITIGATED, NOT UPSTREAM FIXED: ${advisory}`);
    console.log(`Affected dependency entries: ${names.join(", ")}`);
  }
  console.log("No other known advisories reported; installed braces guard verified.");
}
