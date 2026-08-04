import { spawnSync } from "node:child_process";


const npmExecPath = process.env.npm_execpath;

if (!npmExecPath) {
  throw new Error("npm_execpath is required to run the hosting build");
}

const result = spawnSync(process.execPath, [npmExecPath, "run", "build"], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    SITES_HOSTING_BUILD: "1",
  },
  stdio: "inherit",
});

if (result.error) {
  throw result.error;
}

process.exitCode = result.status ?? 1;
