import assert from "node:assert/strict";
import test from "node:test";

const baseUrl = process.env.HANGAR_TEST_URL;
if (!baseUrl) throw new Error("HANGAR_TEST_URL is required.");

test("renders the hangar overview without inventing operational data", async () => {
  const response = await fetch(`${baseUrl}/`, { headers: { accept: "text/html" } });

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /Research Factory Hangar/);
  assert.match(html, /One hundred stations\. One evidence standard\./);
  assert.match(html, /readiness-value">100</);
  assert.match(html, /catalogued stations/);
  assert.match(html, /stat-card stat-card-safe"><strong>0/);
  assert.match(html, /live investigations claimed/);
  assert.match(html, /Synthetic commissioning[^<]*not scientific evidence/i);
  assert.match(html, /href="\/tutorial"[^>]*>Tutorial</);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("renders a foundational station with its exact-proof boundary", async () => {
  const response = await fetch(`${baseUrl}/workbenches/99`, {
    headers: { accept: "text/html" },
  });

  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /WB-099/);
  assert.match(html, /Riemann Hypothesis/);
  assert.match(html, /Zero logical tolerance/);
  assert.match(html, /not scientific evidence/i);
});

test("renders the synthetic workflow tutorial with captions and a transcript", async () => {
  const response = await fetch(`${baseUrl}/tutorial`, {
    headers: { accept: "text/html" },
  });

  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /See the whole workflow in two and a half minutes/);
  assert.match(html, /research-factory-hangar-workflow\.mp4/);
  assert.match(html, /research-factory-hangar-workflow\.vtt/);
  assert.match(html, /NO SCIENTIFIC CREDIT/);
  assert.match(html, /Read the complete narration transcript/);
});
