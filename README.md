# Research Factory Hangar

The Hangar is the construction and synthetic-commissioning workspace for the
Research Factory. It maps all 100 proposed workbenches and provides operational
infrastructure for building their contracts, runners, measurement plans and
review plumbing.

It is deliberately **not** a scientific execution or promotion surface.

## Scope boundary

The application accepts only two operating modes:

- `HANGAR_CONSTRUCTION`
- `SYNTHETIC_COMMISSIONING`

Every work order and event is structurally fixed to:

```text
scientific_evidence = false
counts_as_independent_reproduction = false
eligible_for_promotion = false
```

There are no result, rerun, evidence, holdout, upload, dispatch or promotion
endpoints. Live research remains in the separate factory control plane.

## What is implemented

- a verified, searchable catalogue of 100 objective workbench briefs;
- station detail pages with hard gates, benchmarks and economic/physical
  guardrails;
- attributed construction and synthetic-commissioning work orders;
- command-based, revision-checked work-order transitions;
- a registry for non-promotion runner interfaces;
- append-only operational activity with database triggers rejecting updates and
  deletes;
- private-workspace identity from the hosting platform's authenticated user
  headers;
- a local preview identity restricted to synthetic commissioning;
- a system-boundary view describing the future proposal-only handoff.

The bundled catalogue is byte-identical to
`research_factory_100_workbenches.json` at the project root:

```text
SHA-256 9b37a47c265e916cbf460f4dd0120b02b01fa800b104017b117ba2fc40644cd5
```

## Routes

```text
/                   Hangar readiness overview
/workbenches        Search and filter all 100 stations
/workbenches/:id    Full station brief
/operations         Construction and commissioning shift board
/runners            Non-promotion runner registry
/history            Searchable append-only activity
/architecture       Trust boundaries and future handoff
```

## Development

Node.js 22.13 or newer is required.

```powershell
npm.cmd ci --ignore-scripts --prefer-offline --no-audit --no-fund
npm.cmd run dev
```

The project uses a Sites/Vinext Cloudflare Worker and a project-local D1 database.
The application performs an idempotent schema bootstrap for local development;
the tracked Drizzle migration is the deployment schema.

## Verification

```powershell
npm.cmd run catalogue:verify
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
```

The test suite builds the site, starts its real local Worker runtime, renders
representative pages, and exercises negative governance paths. It asserts that
live research mode, client-supplied promotion fields, promotion-grade runners
and arbitrary status writes are rejected.

## Deployment

`.openai/hosting.json` requests a separate D1 binding named `DB` and no R2
bucket. Deploy this site privately. The hosting access policy establishes
workspace membership; application mutations use the stable
`oai-authenticated-user-id` header injected by the platform.

Construction may eventually export a handoff proposal containing contracts and
tool hashes. Such a proposal can request separate control-plane review only. It
must never create a live round, carry synthetic reproduction credit, or append
Hangar events to the scientific ledger.
