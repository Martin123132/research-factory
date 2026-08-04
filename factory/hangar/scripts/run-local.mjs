import { spawnSync } from "node:child_process";


const allowedScripts = new Set(["build", "dev:raw"]);
const script = process.argv[2];
const npmExecPath = process.env.npm_execpath;

if (!allowedScripts.has(script)) {
  throw new Error(`unsupported local script: ${script ?? "<missing>"}`);
}
if (!npmExecPath) {
  throw new Error("npm_execpath is required to run a local Hangar command");
}

const result = spawnSync(process.execPath, [npmExecPath, "run", script], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    LOCAL_NODE_COMPAT: "1",
  },
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

process.exitCode = result.status ?? 1;
