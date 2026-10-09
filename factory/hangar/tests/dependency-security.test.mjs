import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const sharp = require("sharp");
const { SourceMapConsumer, SourceMapGenerator } = require("source-map-js");

// Compatibility smoke tests for the patched dependencies. The separate npm
// audit gate checks advisories; these fixtures are not security certification.
test("patched image tooling still rasterizes and resizes an SVG", async () => {
  const svg = Buffer.from(
    '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
    + '<rect width="4" height="4" fill="blue"/></svg>',
  );
  const png = await sharp(svg).resize(8, 8).png().toBuffer();
  const metadata = await sharp(png).metadata();
  assert.equal(metadata.format, "png");
  assert.equal(metadata.width, 8);
  assert.equal(metadata.height, 8);
});

test("patched source-map tooling preserves original source positions", () => {
  const generator = new SourceMapGenerator({ file: "output.js" });
  generator.addMapping({
    source: "input.js",
    original: { line: 1, column: 0 },
    generated: { line: 2, column: 3 },
  });
  const consumer = new SourceMapConsumer(generator.toJSON());
  assert.deepEqual(consumer.originalPositionFor({ line: 2, column: 3 }), {
    source: "input.js", line: 1, column: 0, name: null,
  });
});
