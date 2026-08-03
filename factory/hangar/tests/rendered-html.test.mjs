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
  assert.match(html, /deterministic station kits/);
  assert.match(html, /3<\/strong><span>fitted or adapter-bound stations/);
  assert.match(html, /WB-002 now has a closed, hashed exact-compression dossier/);
  assert.match(html, /WB-013 now has an exact symmetric-matrix route verifier/);
  assert.match(html, /stat-card stat-card-safe"><strong>0/);
  assert.match(html, /live investigations enabled/);
  assert.match(html, /Synthetic commissioning[^<]*not scientific evidence/i);
  assert.match(html, /href="\/tutorial"[^>]*>Tutorial</);
  assert.match(html, /href="\/standards"[^>]*>Standards</);
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
  assert.match(html, /CONTRACT DRAFT/);
  assert.match(html, /gates remain before live work/);
  assert.match(html, /not scientific evidence/i);
});

test("renders WB-002 as adapter-bound without claiming commissioning", async () => {
  const response = await fetch(`${baseUrl}/workbenches/2`, {
    headers: { accept: "text/html" },
  });

  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /WB-002/);
  assert.match(html, /ADAPTER BOUND/);
  assert.match(html, /DIGITAL COMPRESSION V1/);
  assert.match(html, /CONTRACT DRAFT/);
  assert.match(html, /adapter-bound does not mean commissioned/i);
});

test("renders WB-013 as a narrowly adapter-bound symmetric TSP station", async () => {
  const response = await fetch(`${baseUrl}/workbenches/13`, {
    headers: { accept: "text/html" },
  });

  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /WB-013/);
  assert.match(html, /Travelling-salesperson route kernel/);
  assert.match(html, /ADAPTER BOUND/);
  assert.match(html, /DIGITAL OPTIMIZATION V1/);
  assert.match(html, /CONTRACT DRAFT/);
  assert.match(html, /adapter-bound does not mean commissioned/i);
});

test("renders the fail-closed Contract v1 standard and downloadable artifacts", async () => {
  const response = await fetch(`${baseUrl}/standards`, {
    headers: { accept: "text/html" },
  });

  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Workbench Contract v1/);
  assert.match(html, /Exactly two distinct accountable humans/);
  assert.match(html, /Factory standard \/ version (?:<!-- -->)?1\.2\.0/);
  assert.match(html, /Contributors retain the rights they lawfully hold/);
  assert.match(html, /commit conclusions and evidence hashes before either result is revealed/i);
  assert.match(html, /stage-number mono">99</);
  assert.match(html, /DIGITAL_COMPRESSION_V1/);
  assert.match(html, /DIGITAL_OPTIMIZATION_V1/);
  assert.match(html, /3<!-- --> runnable entry gates/);
  assert.match(html, /Contract draft/);
  assert.match(html, /href="\/workbench-contracts-v1\.json"/);
  assert.match(html, /href="\/workbench-contract-v1\.schema\.json"/);
  assert.match(html, /href="\/rights-and-ip-v1\.schema\.json"/);
  assert.match(html, /href="\/contribution-ledger-v1\.schema\.json"/);
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

test("renders a construction-only contributor entrance", async () => {
  const response = await fetch(`${baseUrl}/contribute`);
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Clock in\. Leave the bench clearer than you found it\./);
  assert.match(html, /PUBLIC LANE/);
  assert.match(html, /Scientific promotion remains locked/);
  assert.match(html, /Your work stays yours/);
  assert.match(html, /No inherited licence/);
  assert.doesNotMatch(html, /Submit a scientific reproduction/);
});
