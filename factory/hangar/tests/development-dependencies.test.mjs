import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { assessAudit } from "../scripts/audit-dependencies.mjs";
import { guardedSource, verifyOrInstallGuards } from "../scripts/guard-braces.mjs";

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL("../", import.meta.url));
const braces = require("braces");
const glob = require("fast-glob");
const fflate = require("fflate");

function runChild(code) {
  const child = spawnSync(process.execPath, ["--input-type=module", "-e", code], {
    cwd: root, encoding: "utf8", timeout: 10_000,
  });
  assert.ifError(child.error);
  assert.equal(child.status, 0, child.stderr || child.stdout);
}

test("braces guard is exact, idempotent and fails closed on missing/tampered source", () => {
  assert.ok(verifyOrInstallGuards().length > 0);
  const source = readFileSync(require.resolve("braces/lib/parse.js"), "utf8");
  assert.equal(guardedSource(source), source);
  const original = source.replace(/    \/\/ Research Factory local mitigation[^]*?\n    }\n\n/, "");
  assert.notEqual(original, source);
  assert.throws(() => guardedSource(original, true), /Missing braces depth guard/);
  assert.equal(guardedSource(original), source);
  assert.throws(() => guardedSource(source + "\n", true), /Unrecognised/);
  assert.throws(() => guardedSource(source.replace("stack.length > 100", "stack.length > 9999")), /Unrecognised/);
});

test("normal brace expansion, literals, ranges and fast-glob retain their semantics", () => {
  assert.deepEqual(braces.expand("a/{b,c{1..2}}/d"), ["a/b/d", "a/c1/d", "a/c2/d"]);
  assert.equal(braces.compile("a/{b,c}/d"), "a/(b|c)/d");
  assert.deepEqual(braces.expand("x\\{a,b\\}"), ["x{a,b}"]);
  for (const literal of ["\"" + "{".repeat(200) + "\"", "[" + "{".repeat(200) + "]"]) {
    assert.doesNotThrow(() => braces.parse(literal));
  }
  assert.doesNotThrow(() => braces.compile("{".repeat(100) + "x" + "}".repeat(100)));
  assert.deepEqual(glob.sync("db/{schema,missing}.ts", { cwd: root }), ["db/schema.ts"]);
  assert.deepEqual(glob.sync(["tests/*.test.mjs", "!tests/development-dependencies.test.mjs"], { cwd: root })
    .includes("tests/dependency-security.test.mjs"), true);
});

test("deep brace and parenthesis inputs fail promptly at the parser boundary", () => {
  runChild(`
    import assert from 'node:assert/strict';
    import braces from 'braces';
    const methods = [braces, braces.parse, braces.compile, braces.expand, braces.stringify];
    for (const [open, close] of [['{', '}'], ['(', ')'], ['{(', ')}']]) {
      for (const depth of [101, 2000]) {
        for (const balanced of [true, false]) {
          const input = open.repeat(depth) + 'x' + (balanced ? close.repeat(depth) : '');
          for (const method of methods) {
            assert.throws(() => method(input), {name: 'SyntaxError', message: /nesting exceeds 100/});
          }
        }
      }
    }
  `);
});

function auditFixture() {
  return {
    auditReportVersion: 2,
    metadata: { vulnerabilities: { total: 2 } },
    vulnerabilities: {
      braces: { nodes: ["node_modules/braces"], via: [{ name: "braces", severity: "high",
        range: "<=3.0.3", url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm" }] },
      micromatch: { via: ["braces"] },
    },
  };
}

test("audit accepts only the documented advisory with verified installed paths", () => {
  assert.deepEqual(assessAudit(auditFixture(), ["node_modules/braces"]), ["braces", "micromatch"]);
  assert.throws(() => assessAudit(auditFixture(), []), /Unmitigated/);
  assert.throws(() => assessAudit({ error: "network unavailable" }, []), /Invalid/);
  for (const mutate of [
    (r) => { r.vulnerabilities.braces.via[0].url += "-new"; },
    (r) => { r.vulnerabilities.braces.nodes.push("node_modules/other/node_modules/braces"); },
    (r) => { r.vulnerabilities.micromatch.via.push({ name: "micromatch", url: "new-advisory" }); },
    (r) => { r.vulnerabilities.micromatch.via = ["missing"]; },
    (r) => { r.vulnerabilities.micromatch.via = ["micromatch"]; },
    (r) => { r.vulnerabilities.braces.via = []; },
    (r) => { r.metadata.vulnerabilities.total = 0; },
  ]) {
    const report = auditFixture();
    mutate(report);
    assert.throws(() => assessAudit(report, ["node_modules/braces"]));
  }
});

test("patched fflate round-trips compressed ZIP and zlib content", () => {
  const data = new TextEncoder().encode("Factory commissioning fixture. ".repeat(100));
  assert.deepEqual(fflate.unzipSync(fflate.zipSync({ "fixture.txt": data }))["fixture.txt"], data);
  assert.deepEqual(fflate.unzlibSync(fflate.zlibSync(data)), data);
});

test("patched fflate rejects ZIP64 entries missing the ZIP64 extra field", () => {
  runChild(`
    import assert from 'node:assert/strict';
    import { unzipSync } from 'fflate';
    // Synthetic ZIP64 directory: one entry, sentinel compressed size, no extra field.
    const zip = Buffer.alloc(144);
    zip.writeUInt32LE(0x02014b50, 0);
    zip.writeUInt32LE(0xffffffff, 20);
    zip.writeUInt32LE(0x06064b50, 46);
    zip.writeUInt32LE(1, 46 + 32);
    zip.writeUInt32LE(0, 46 + 48);
    zip.writeUInt32LE(0x07064b50, 102);
    zip.writeUInt32LE(46, 102 + 8);
    zip.writeUInt32LE(0x06054b50, 122);
    zip.writeUInt16LE(0xffff, 122 + 8);
    assert.throws(() => unzipSync(zip), /invalid zip data/);
  `);
});

test("OG layout/font tooling still renders SVG and rasterizes a PNG", async () => {
  const satori = require("satori").default;
  const { createElement } = await import("react");
  const font = readFileSync(join(dirname(require.resolve("@vercel/og")), "Geist-Regular.ttf"));
  const svg = await satori(createElement("div", {
    style: { display: "flex", color: "black", background: "white", fontSize: 24 },
  }, "Factory"), { width: 200, height: 80, fonts: [{ name: "Geist", data: font, weight: 400 }] });
  const png = await require("sharp")(Buffer.from(svg)).png().toBuffer();
  const metadata = await require("sharp")(png).metadata();
  assert.equal(metadata.format, "png");
  assert.equal(metadata.width, 200);
  assert.equal(metadata.height, 80);
});

test("legacy esbuild-kit transform APIs work with the scoped esbuild upgrade", async () => {
  const core = require("@esbuild-kit/core-utils");
  const source = "const value: number = 42; export default value;";
  for (const result of [core.transformSync(source, join(root, "fixture.ts")),
    await core.transform(source, join(root, "fixture.ts"))]) {
    assert.match(result.code, /42/);
    assert.doesNotMatch(result.code, /: number/);
    assert.ok(result.map);
  }
});

test("the scoped esbuild server does not grant arbitrary website CORS access", async () => {
  const coreRequire = createRequire(require.resolve("@esbuild-kit/core-utils"));
  const esbuild = coreRequire("esbuild");
  const context = await esbuild.context({
    stdin: { contents: "console.log(42)", loader: "js" },
    outfile: "fixture.js", write: false,
  });
  try {
    const server = await context.serve({ host: "127.0.0.1", port: 0 });
    const response = await fetch(`http://127.0.0.1:${server.port}/fixture.js`, {
      headers: { Origin: "https://untrusted.invalid" }, signal: AbortSignal.timeout(5000),
    });
    assert.equal(response.status, 200);
    assert.match(await response.text(), /42/);
    assert.equal(response.headers.get("access-control-allow-origin"), null);
  } finally {
    await context.dispose();
  }
});

test("Drizzle generates the actual TypeScript schema in an isolated temporary output", () => {
  const temp = mkdtempSync(join(tmpdir(), "factory-drizzle-security-"));
  try {
    const child = spawnSync(process.execPath, [join(dirname(require.resolve("drizzle-kit")), "bin.cjs"),
      "generate", "--dialect", "sqlite", "--schema", "./db/schema.ts", "--out", temp], {
      cwd: root, encoding: "utf8", timeout: 60_000,
    });
    assert.ifError(child.error);
    assert.equal(child.status, 0, child.stderr || child.stdout);
    const files = readdirSync(temp).filter((name) => name.endsWith(".sql"));
    assert.equal(files.length, 1, child.stdout);
    const sql = readFileSync(join(temp, files[0]), "utf8");
    for (const table of ["schema_metadata", "work_orders", "shift_reports", "runner_profiles", "activity_events"]) {
      assert.ok(sql.includes("CREATE TABLE `" + table + "`"), table);
    }
    assert.match(sql, /work_orders_no_promotion_check/);
  } finally {
    assert.equal(dirname(resolve(temp)), resolve(tmpdir()));
    assert.ok(temp.startsWith(join(tmpdir(), "factory-drizzle-security-")));
    rmSync(temp, { recursive: true, force: true });
  }
});
