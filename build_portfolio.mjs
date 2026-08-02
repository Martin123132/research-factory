import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const cwd = process.cwd();
const algorithmPath = resolve(cwd, "algorithms_workbenches_47.md");
const engineeringPath = resolve(cwd, "engineering_workbenches_47.md");

const CATEGORY_MAP = new Map([
  ["Compression, storage and representation", { category: "Compression & storage", short: "Compression", lane: "Digital" }],
  ["Routing, scheduling, packing and logistics", { category: "Routing & logistics", short: "Routing", lane: "Digital" }],
  ["Communications and sensing", { category: "Communications & sensing", short: "Comms & sensing", lane: "Digital / device" }],
  ["Software, compute and databases", { category: "Software & compute", short: "Software & compute", lane: "Digital" }],
  ["Energy, power and thermal systems", { category: "Energy, power & thermal", short: "Energy & thermal", lane: "Simulation to lab" }],
  ["Manufacturing, materials and recycling", { category: "Manufacturing & materials", short: "Manufacturing", lane: "Lab / pilot" }],
  ["Water, agriculture, environment and civil infrastructure", { category: "Water, environment & civil", short: "Water & civil", lane: "Simulation to field" }],
  ["Robotics, control and transport", { category: "Robotics & transport", short: "Robotics & transport", lane: "Simulation to physical" }],
]);

function cleanMarkdown(value) {
  return value
    .replaceAll("**", "")
    .replaceAll("`", "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseLinks(value) {
  return [...value.matchAll(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g)].map((match) => ({
    label: cleanMarkdown(match[1]),
    url: match[2],
  }));
}

function parseDocument(path, idOffset) {
  const lines = readFileSync(path, "utf8").split(/\r?\n/);
  let heading = null;
  const rows = [];

  for (const line of lines) {
    const headingMatch = line.match(/^##\s+(.+?)(?:\s+[—-]\s+\d+|\s+\(\d+\))\s*$/);
    if (headingMatch) {
      heading = headingMatch[1].trim();
      continue;
    }

    const itemMatch = line.match(/^(\d+)\.\s+\*\*(.+?)\.\*\*\s+(.+)$/);
    if (!itemMatch || !heading || !CATEGORY_MAP.has(heading)) continue;

    const localId = Number(itemMatch[1]);
    const title = cleanMarkdown(itemMatch[2]);
    const body = cleanMarkdown(itemMatch[3]);
    const links = parseLinks(itemMatch[3]);

    let gate = "";
    let guardrail = "";
    if (body.startsWith("Gate:")) {
      const match = body.match(/^Gate:\s*(.*?)\s+Economic guardrail:\s*(.*?)\s+Sources?:\s*(.*)$/);
      if (!match) throw new Error(`Could not parse algorithm entry ${localId}: ${body}`);
      gate = match[1];
      guardrail = match[2];
    } else if (body.startsWith("Pass gates:")) {
      const match = body.match(/^Pass gates:\s*(.*?)\s+Economic guardrail:\s*(.*?)\s+Primary [^:]+:\s*(.*)$/);
      if (!match) throw new Error(`Could not parse engineering entry ${localId}: ${body}`);
      gate = match[1];
      guardrail = match[2];
    } else {
      throw new Error(`Unknown entry format ${localId}: ${body}`);
    }

    const meta = CATEGORY_MAP.get(heading);
    rows.push({
      id: idOffset + localId,
      category: meta.category,
      short_category: meta.short,
      evidence_lane: meta.lane,
      workbench: title,
      hard_gate_and_score: cleanMarkdown(gate),
      economic_or_physical_guardrail: cleanMarkdown(guardrail),
      benchmark: links.map((link) => link.label).join("; "),
      reference_url: links.map((link) => link.url).join(" | "),
      starter_pack: "Reproduce the pinned baseline, pass the public verifier, then submit one sealed candidate against hidden holdouts.",
      track: "Practical improvement",
      ...(idOffset + localId === 1
        ? {
            implementation_status: "pilot_round_open",
            contract_version: "0.2.0",
            factory_path: "factory/workbenches/wb001_lossless_compression",
            control_plane_path: "factory/control_plane",
            active_round: "factory/rounds/WB001-PILOT-001/round.json",
          }
        : {}),
    });
  }

  return rows;
}

const claySource = "https://www.claymath.org/library/monographs/MPPc.pdf";
const clayRules = "https://www.claymath.org/millennium-problems/rules/";
const clayRows = [
  {
    id: 95,
    workbench: "P versus NP",
    starter_pack: "In a roughly four-hour Colab, reproduce a small Cook–Levin-style reduction from a frozen verifier to SAT, check witnesses in both directions, benchmark formula growth, and identify a planted step that confuses fast finite cases with a worst-case polynomial proof.",
    hard_gate_and_score: "A complete proof of P=NP or P≠NP under the official definitions. Every reduction, quantifier and asymptotic bound must survive dependency checking; experiments or a fast solver on finite instances cannot satisfy the proof gate.",
  },
  {
    id: 96,
    workbench: "Navier–Stokes existence and smoothness",
    starter_pack: "Run a manufactured-solution and mesh-refinement study, reproduce an energy-balance check, perturb timestep and resolution, and write a one-page boundary explaining exactly why numerical regularity is evidence rather than a global proof.",
    hard_gate_and_score: "A proof satisfying one of the official existence/smoothness or breakdown statements, with the stated dimension, domain, initial data and function spaces. All estimates and limiting arguments are exact gates; stable simulations do not substitute for proof.",
  },
  {
    id: 97,
    workbench: "Hodge Conjecture",
    starter_pack: "Use SageMath or Macaulay2 to reproduce cycle/cohomology calculations for supplied known cases, verify rationality and type conditions, catch a planted leap from examples to a universal statement, and export a dependency log.",
    hard_gate_and_score: "A proof or counterexample matching the official statement for rational Hodge classes on nonsingular projective complex varieties. The construction of algebraic cycles and every rationality/field condition must be checked; collections of examples remain evidence only.",
  },
  {
    id: 98,
    workbench: "Birch and Swinnerton–Dyer Conjecture",
    starter_pack: "With SageMath or PARI/GP, reproduce analytic-rank and Mordell–Weil calculations for a frozen set of known elliptic curves, check precision sensitivity, and label every output as theorem, certified computation or numerical evidence.",
    hard_gate_and_score: "A proof of the official rank/order-of-vanishing statement, with analytic continuation, local factors, ranks and any stronger claims separated explicitly. Finite computations on curves cannot satisfy the universal proof gate.",
  },
  {
    id: 99,
    workbench: "Riemann Hypothesis",
    starter_pack: "Run interval-certified zero counting on a fixed finite window, reproduce the functional equation and a known finite theorem or heat-flow calculation, then locate a planted conflation between finite verification and the universal claim.",
    hard_gate_and_score: "Either prove every nontrivial zeta zero has real part one half or provide a rigorously certified counterexample. Domains, analytic continuation, multiplicities and all limit operations are exact; no finite zero count promotes as a solution.",
  },
  {
    id: 100,
    workbench: "Yang–Mills existence and mass gap",
    starter_pack: "Run a small lattice gauge calculation with gauge-invariance tests, Wilson-loop or correlator checks and refinement sensitivity, then explain why a lattice mass proxy does not construct the required continuum theory.",
    hard_gate_and_score: "Construct a nontrivial quantum Yang–Mills theory on R4 with a positive mass gap under the official axiomatic requirements. Gauge invariance, continuum existence and Δ>0 are exact gates; lattice or perturbative evidence alone cannot satisfy them.",
  },
].map((row) => ({
  ...row,
  category: "Clay exact proofs",
  short_category: "Clay proofs",
  evidence_lane: "Exact proof",
  economic_or_physical_guardrail: "Zero logical tolerance. The platform may record internal verification, but must never claim Clay acceptance; the official publication, two-year and general-acceptance process remains external.",
  benchmark: "Clay Mathematics Institute official problem statement and rules",
  reference_url: `${claySource} | ${clayRules}`,
  track: "Foundational exact proof",
}));

const rows = [
  ...parseDocument(algorithmPath, 0),
  ...parseDocument(engineeringPath, 47),
  ...clayRows,
].sort((a, b) => a.id - b.id);

if (rows.length !== 100) throw new Error(`Expected 100 workbenches, found ${rows.length}`);
for (let index = 0; index < rows.length; index += 1) {
  if (rows[index].id !== index + 1) throw new Error(`Missing or duplicate id near ${index + 1}`);
}

const categoryOrder = [
  "Compression & storage",
  "Routing & logistics",
  "Communications & sensing",
  "Software & compute",
  "Energy, power & thermal",
  "Manufacturing & materials",
  "Water, environment & civil",
  "Robotics & transport",
  "Clay exact proofs",
];

const categoryNotes = {
  "Compression & storage": "These are ideal first-floor workbenches: correctness can be exact, benchmark files can be hashed, and the commercial question can be expressed as storage plus compute cost per retained or delivered unit.",
  "Routing & logistics": "Feasibility is checked before distance or makespan. A shorter route, denser pack or faster schedule is invalid if it breaks capacity, time, safety or staffing constraints.",
  "Communications & sensing": "Accuracy is only one axis. Every candidate also carries latency, memory, power, hardware and subgroup or operating-condition gates.",
  "Software & compute": "These workbenches pair exact outputs or official validators with performance, tail latency, memory, energy and price/performance measurements.",
  "Energy, power & thermal": "Simulation is the first gate, not the last. Promotion to deployment requires hardware or laboratory evidence plus reliability, degradation and lifecycle-cost checks.",
  "Manufacturing & materials": "The unit of value is a conforming, durable part or recovered material—not a single flattering coupon, image or classifier score.",
  "Water, environment & civil": "These require mass balance, uncertainty and failure-mode accounting. Field claims remain in a separate lane until replicated outside the development site or season.",
  "Robotics & transport": "Safety constraints are non-tradeable. Simulation can rank candidates, but physical promotion needs controlled trials before any operational use.",
  "Clay exact proofs": "These six use exact logical gates. The four-hour pack tests discipline and vocabulary, not credentials; passing it grants permission to submit work, not scientific credibility or a prize claim.",
};

const categoryCounts = categoryOrder.map((category, order) => {
  const categoryRows = rows.filter((row) => row.category === category);
  return {
    order: order + 1,
    category: categoryRows[0].short_category,
    full_category: category,
    workbenches: categoryRows.length,
    track: category === "Clay exact proofs" ? "Exact proof" : "Practical improvement",
    evidence_lane: categoryRows[0].evidence_lane,
  };
});

const portfolioSource = {
  id: "portfolio_design",
  label: "Curated 100-workbench inventory",
  path: "research_factory_100_workbenches.json",
  query: {
    engine: "duckdb",
    language: "sql",
    sql: "SELECT w.* FROM (SELECT UNNEST(workbenches) AS w FROM read_json_auto('research_factory_100_workbenches.json'))",
    description: "A curated synthesis of 94 benchmarkable practical improvement workbenches and the six unresolved Clay Millennium Prize Problems, frozen on 1 August 2026.",
    tables_used: ["research_factory_100_workbenches.json"],
    filters: ["Exactly 100 entries", "Practical problems require an external verifier and economic or physical guardrail", "Clay lane contains only the six problems listed as unsolved by CMI"],
    metric_definitions: [
      "Total workbenches = count of distinct sequential workbench IDs.",
      "Practical workbenches = entries 1–94 with measurable performance and cost or physical constraints.",
      "Exact-proof workbenches = the six Clay problems officially listed as unsolved on 1 August 2026.",
    ],
  },
};

const clayOpenSource = {
  id: "clay_unsolved",
  label: "Clay Mathematics Institute — unsolved problems",
  href: "https://www.claymath.org/problem/unsolved/",
  query: {
    engine: "web_document",
    description: "Official current list of the six unresolved Millennium Prize Problems.",
  },
};

const clayRulesSource = {
  id: "clay_rules",
  label: "Clay Mathematics Institute — prize rules",
  href: clayRules,
  query: {
    engine: "web_document",
    description: "Official rules for external publication, waiting period and general acceptance.",
  },
};

const cards = [
  {
    id: "total_workbenches",
    description: "Distinct workbench contracts in this launch portfolio.",
    dataset: "summary",
    sourceId: "portfolio_design",
    metrics: [{ label: "Total workbenches", field: "total", format: "number" }],
  },
  {
    id: "practical_workbenches",
    description: "Algorithmic and physical improvement workbenches with measurable external gates.",
    dataset: "summary",
    sourceId: "portfolio_design",
    metrics: [{ label: "Practical workbenches", field: "practical", format: "number" }],
  },
  {
    id: "exact_proof_workbenches",
    description: "The six Millennium Prize Problems that CMI currently lists as unresolved.",
    dataset: "summary",
    sourceId: "portfolio_design",
    metrics: [{ label: "Clay exact-proof lanes", field: "clay", format: "number" }],
  },
  {
    id: "independent_validators",
    description: "Other human owners required to reproduce a candidate before main-repository promotion.",
    dataset: "summary",
    sourceId: "portfolio_design",
    metrics: [{ label: "Independent human validators", field: "validators", format: "number" }],
  },
];

const charts = [{
  id: "category_coverage",
  title: "Launch workbenches by family",
  subtitle: "94 practical improvement contracts and six exact-proof contracts; 100 total",
  type: "bar",
  dataset: "category_counts",
  sourceId: "portfolio_design",
  encodings: {
    x: { field: "category", type: "nominal", label: "Workbench family" },
    y: { field: "workbenches", type: "quantitative", label: "Workbenches", format: "number" },
  },
  yAxisTitle: "Number of workbenches",
  valueFormat: "number",
  layout: "full",
}];

const tables = categoryOrder.map((category, index) => {
  const isClay = category === "Clay exact proofs";
  return {
    id: `workbenches_${index + 1}`,
    title: category,
    subtitle: isClay
      ? "Entry pack is deliberately accessible; promotion remains an exact proof decision."
      : "Correctness and hard constraints are checked before any performance or cost comparison.",
    dataset: `category_${index + 1}`,
    sourceId: "portfolio_design",
    defaultSort: { field: "id", direction: "asc" },
    density: "spacious",
    layout: "full",
    columns: isClay
      ? [
          { field: "id", label: "#", type: "number" },
          { field: "workbench", label: "Problem", type: "text" },
          { field: "starter_pack", label: "Entry pack (~4 hours)", type: "text" },
          { field: "hard_gate_and_score", label: "Exact promotion gate", type: "text" },
          { field: "benchmark", label: "Authority", type: "text" },
        ]
      : [
          { field: "id", label: "#", type: "number" },
          { field: "workbench", label: "Workbench", type: "text" },
          { field: "hard_gate_and_score", label: "Hard pass gate and score", type: "text" },
          { field: "economic_or_physical_guardrail", label: "Economic / physical guardrail", type: "text" },
          { field: "benchmark", label: "Starting benchmark or protocol", type: "text" },
        ],
  };
});

const blocks = [
  { id: "title", type: "markdown", body: "# 100 Workbenches for a Reproducible Human–AI Research Factory" },
  {
    id: "technical_summary",
    type: "markdown",
    sourceId: "portfolio_design",
    body: "## The portfolio is practical enough to launch\n\n**The result is 100 workbench contracts, not 100 vague topics:** 94 are practical improvement frontiers with machine-checkable or physically measurable gates, and six are the still-open Clay problems in a separate exact-proof lane. Every practical row asks two questions in order: *is it correct and safe?* and only then *is it a useful Pareto improvement after time, memory, energy and money are counted?*\n\nTwo unrelated people must each own a blind reproduction before promotion. A failed attempt is still admitted to the searchable attempt graph when its scope, artifacts and failure are reproducible; it simply does not enter the verified-solution repository.",
  },
  { id: "headline_metrics", type: "metric-strip", cardIds: cards.map((card) => card.id) },
  {
    id: "coverage_finding",
    type: "markdown",
    sourceId: "portfolio_design",
    body: "## Most of the factory can produce useful evidence immediately\n\nThe portfolio deliberately weights digital optimisation and standardized engineering tests, where a worker can compare a candidate with a pinned baseline without anyone voting on whether the output *looks clever*. The six proof problems are visible but isolated so their prestige cannot weaken the ordinary admission standard.",
  },
  { id: "coverage_chart", type: "chart", chartId: "category_coverage", layout: "full" },
  {
    id: "scope_definitions",
    type: "markdown",
    body: "## A workbench is a versioned measurement contract\n\nEach workbench freezes: the question and scope; public development inputs; sealed holdouts; dataset and environment hashes; a correctness/safety verifier; baseline artifacts; primary and secondary metrics; tolerances or statistical tests; resource ceilings; an economic or physical guardrail; and the evidence bundle required for reproduction.\n\n**Better** means a new non-dominated point after every hard gate passes. It does not mean winning one metric by spending absurd compute or shifting cost elsewhere. Exact outputs use zero tolerance; runtimes use controlled repeated measurements; stochastic results use predeclared seeds and uncertainty; physical results use calibrated uncertainty and replicate specimens.",
  },
  {
    id: "admission_method",
    type: "markdown",
    body: "## Promotion is blind, two-person and failure-aware\n\n1. The author freezes code, method, environment, data hashes, claimed result and cost vector.\n2. The evaluator hides both the claim and holdout answers.\n3. Two unrelated human owners independently rerun the locked artifact without seeing one another's result.\n4. The evaluator checks hard gates, then compares results under the workbench's predeclared rule.\n5. Two passes make the candidate eligible for the verified repository; disagreement goes to a blind tie-break and divergence review.\n6. Reproducible dead ends enter the attempt graph as `RERUN_CONFIRMED_NO_GAIN`, `BOUNDARY_FOUND` or another typed negative result. `UNRUNNABLE`, `INVALID` and `DISPUTED` remain distinct states.",
  },
];

categoryOrder.forEach((category, index) => {
  blocks.push({
    id: `section_${index + 1}`,
    type: "markdown",
    body: `## ${category}\n\n${categoryNotes[category]}`,
  });
  blocks.push({
    id: `table_${index + 1}`,
    type: "table",
    tableId: `workbenches_${index + 1}`,
    layout: "full",
  });
});

blocks.push(
  {
    id: "clay_process",
    type: "markdown",
    sourceId: "clay_rules",
    body: "## The Clay lane must never imply that the platform awards a proof\n\nThe starter pack is a seriousness and scientific-hygiene gate, not an intelligence test and not a credential test. Target about four hours on free Colab-class compute, provide an accessibility/time alternative, and ask the entrant to reproduce a known result, catch a planted invalid inference, preserve a signed log, and distinguish finite evidence from a universal theorem.\n\nAfter that, a proposed solution still needs an exact theorem statement, definitions, lemma dependency graph, citation and assumption audit, adversarial counterexample search, formalization where feasible, two independent human-owned reproductions and specialist review. Clay's own process remains authoritative: CMI does not accept direct submissions and requires qualifying publication, at least two years, and general acceptance before it will consider a solution.",
  },
  {
    id: "limitations",
    type: "markdown",
    body: "## The gates remove nonsense; they do not remove experimental reality\n\nA frozen benchmark can be overfit, so each practical lane needs rotating sealed holdouts and later out-of-distribution or field confirmation. Physical work also needs laboratories, calibrated instruments and enough replicate units to estimate variance. A candidate that wins in simulation is labelled *simulation-verified*, not *field-verified*. Medical, infrastructure and safety-critical outputs remain non-deployable until their separate regulatory and safety processes are satisfied.\n\nThe list is a launch portfolio, not a claim that these are the only worthwhile questions or that every benchmark is permanent. Workbench versions should be retired when saturated, leaked or no longer economically representative.",
  },
  {
    id: "next_steps",
    type: "markdown",
    body: "## Start with three workbenches that exercise different evidence types\n\n1. **General-purpose lossless compression:** exact round trip, cheap runners and an immediately understandable cost model.\n2. **Capacitated vehicle routing:** exact feasibility plus a multi-objective distance/time/compute frontier.\n3. **NIST additive-manufacturing prediction:** a genuinely physical blind benchmark that tests the hand-off from computation to laboratory truth.\n\nBuild one shared `workbench.yaml` schema and evaluator, then instantiate those three. Do not build 100 bespoke platforms first; prove that one admission protocol can carry three very different truth conditions.",
  },
  {
    id: "further_questions",
    type: "markdown",
    body: "## Decisions for the first repository version\n\n- Which three workbenches receive launch maintainers and compute budget?\n- What minimum economic improvement is meaningful in each lane: a fixed percentage, a confidence-bound gain, or any strict Pareto improvement?\n- How often are hidden holdouts rotated, and who is allowed to construct them?\n- Which negative-result types are strong enough to prevent agents repeating the same search region?\n- Which identity check is proportionate for ordinary work, and when should organizational separation be required?",
  },
);

const datasets = {
  summary: [{ total: 100, practical: 94, clay: 6, validators: 2 }],
  category_counts: categoryCounts,
};
categoryOrder.forEach((category, index) => {
  datasets[`category_${index + 1}`] = rows.filter((row) => row.category === category);
});

const artifact = {
  surface: "report",
  manifest: {
    version: 1,
    surface: "report",
    title: "100 Workbenches for a Reproducible Human–AI Research Factory",
    description: "A launch portfolio of 94 practical benchmarkable research workbenches and six exact-proof Clay lanes.",
    generatedAt: "2026-08-01T00:00:00Z",
    cards,
    charts,
    tables,
    sources: [portfolioSource, clayOpenSource, clayRulesSource],
    blocks,
  },
  snapshot: {
    version: 1,
    generatedAt: "2026-08-01T00:00:00Z",
    status: "ready",
    datasets,
  },
  sources: [portfolioSource, clayOpenSource, clayRulesSource],
  package_info: {
    root: "research-factory-portfolio",
    manifestPath: "research_factory_100_report_artifact.json",
    snapshotPath: "research_factory_100_report_artifact.json",
  },
};

const portfolioOutput = resolve(cwd, "research_factory_100_workbenches.json");
const artifactOutput = resolve(cwd, "research_factory_100_report_artifact.json");
writeFileSync(portfolioOutput, `${JSON.stringify({ version: 1, generated_at: "2026-08-01", workbenches: rows }, null, 2)}\n`, "utf8");
writeFileSync(artifactOutput, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");

console.log(JSON.stringify({
  workbenches: rows.length,
  practical: rows.filter((row) => row.track === "Practical improvement").length,
  clay: clayRows.length,
  categories: Object.fromEntries(categoryCounts.map((row) => [row.full_category, row.workbenches])),
  outputs: [portfolioOutput, artifactOutput],
}, null, 2));
