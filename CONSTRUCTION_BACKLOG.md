# Pick-up-ready construction backlog

These packets are seed jobs for the public construction lane. A maintainer can
copy one into the `Construction task` issue form without adding hidden
requirements. Completing one carries zero scientific, reproduction or
promotion credit.

## CT-001 — Clean-clone quickstart verification

- **Scope:** `FACTORY-WIDE / HANGAR_CONSTRUCTION`
- **Deliverable:** `CONTRIBUTOR_COMPATIBILITY.md`
- **Done when:** Windows plus one of Linux, macOS or Colab have independently
  followed `CONTRIBUTOR_QUICKSTART.md`; exact commands, versions, durations and
  any divergence are recorded.
- **Checks:** every claimed command has its exit status; failures are retained
  rather than rewritten as passes.
- **Licence:** CC-BY-4.0.
- **Skills required:** command-line basics; no scientific background.

## CT-002 — Asset-provenance schema and negative tests

- **Scope:** `FACTORY-WIDE / HANGAR_CONSTRUCTION`
- **Deliverables:** a closed JSON Schema for `ASSET_PROVENANCE.json` and focused
  unit tests for the existing verifier.
- **Done when:** schema and verifier agree on every required field and path
  rule without weakening the exact tracked-media coverage check.
- **Checks:** tampered hash, missing media entry, duplicate path, traversal,
  symlink and undeclared new media all fail; the current asset set passes.
- **Licence:** Apache-2.0.
- **Skills required:** introductory Python and JSON.

## CT-003 — Contributor-page accessibility audit

- **Scope:** `FACTORY-WIDE / HANGAR_CONSTRUCTION`
- **Deliverable:** `factory/hangar/ACCESSIBILITY_AUDIT.md` with reproducible
  observations and separate follow-up tasks for defects.
- **Done when:** keyboard order, visible focus, headings, landmarks, link names,
  zoom at 200%, reduced motion and narrow-screen reading order are checked on
  `/contribute`, `/workbenches` and `/operations`.
- **Checks:** browser/version and exact reproduction steps accompany every
  finding; the audit itself does not silently change UI behavior.
- **Licence:** CC-BY-4.0.
- **Skills required:** careful browser use; no programming required.

## CT-004 — Structured end-of-shift report design

- **Scope:** `FACTORY-WIDE / HANGAR_CONSTRUCTION`
- **Deliverable:** a closed JSON Schema and state-transition proposal for an
  append-only Hangar shift report containing attempted work, outcome class,
  artifact references, blockers and next leads.
- **Done when:** the design proves all scientific fields remain false, reports
  cannot rewrite history, and a worker can log a useful no-gain shift without
  closing the work order.
- **Checks:** examples cover progress, no gain, blocked and unrunnable outcomes;
  live-research and validator-verdict fields are rejected.
- **Licence:** Apache-2.0 for the schema; CC-BY-4.0 for explanatory prose.
- **Skills required:** basic data modelling; implementation is a later task.

## CT-005 — Catalogue reference provenance batch

- **Scope:** `WB-001` through `WB-010 / HANGAR_CONSTRUCTION`
- **Deliverable:** a dated reference manifest containing authoritative URLs,
  retrieval dates, page hashes where permitted and a note for unavailable or
  ambiguous sources.
- **Done when:** all ten rows are accounted for without copying restricted
  datasets or claiming that an accessible page grants redistribution rights.
- **Checks:** station IDs match the canonical catalogue and every recorded hash
  identifies the exact bytes retrieved.
- **Licence:** CC0-1.0 for factual manifest fields; upstream terms remain intact.
- **Skills required:** careful source checking; no claim-solving required.
