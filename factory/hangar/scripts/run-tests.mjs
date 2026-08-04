import { spawn } from "node:child_process";
import { readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const existingUrl = process.env.HANGAR_TEST_URL;
let server;
let serverOutput = "";

async function waitUntilReady(url) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The development worker is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for ${url}.\n${serverOutput}`);
}

function runNodeTests(url, files) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["--test", ...files], {
      cwd: projectRoot,
      env: { ...process.env, HANGAR_TEST_URL: url },
      stdio: "inherit",
    });
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 1));
  });
}

try {
  let url = existingUrl;
  if (!url) {
    const port = 4300 + (process.pid % 300);
    url = `http://localhost:${port}`;
    const cli = fileURLToPath(
      new URL("../node_modules/vinext/dist/cli.js", import.meta.url),
    );
    server = spawn(process.execPath, [cli, "dev", "--port", String(port)], {
      cwd: projectRoot,
      env: { ...process.env, LOCAL_NODE_COMPAT: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    server.stdout.on("data", (chunk) => { serverOutput += chunk.toString(); });
    server.stderr.on("data", (chunk) => { serverOutput += chunk.toString(); });
    await waitUntilReady(url);
  }

  const files = (await readdir(new URL("../tests/", import.meta.url)))
    .filter((file) => file.endsWith(".test.mjs"))
    .map((file) => `tests/${file}`)
    .sort();
  process.exitCode = await runNodeTests(url, files);
} finally {
  server?.kill();
}
