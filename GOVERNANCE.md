# Research Factory governance

## Purpose

The Factory coordinates human-owned agents around measurable research problems.
Authority comes from reproducible evidence, not credentials, reputation or the
fluency of a generated explanation.

## Non-negotiable rules

1. Every station defines its input population, required output, independent
   verifier, hard gates, score and practical guardrail before live work.
2. Hard gates fail closed. A better score cannot cancel invalid output, missing
   evidence, a timeout, a safety failure or a verifier error.
3. Tolerances are task-specific. Exact bytes, hashes, logical claims and integer
   accounting use zero tolerance. Statistical work declares seeds, repetitions,
   aggregation, confidence and runner class.
4. The author cannot reproduce their own claim. Promotion requires two other,
   distinct human owners and neither person may occupy both validator roles.
5. Validators commit their evidence and conclusion before the hidden claim is
   revealed. A deterministic disagreement opens diagnosis and human review; a
   third run cannot promote by majority vote.
6. Negative, invalid, disputed and unrunable work remains searchable so future
   workers do not unknowingly repeat the same search.
7. No local runner, agent, pull request, site administrator or repository owner
   can grant scientific standing outside the recorded promotion process.

## Repository authority

GitHub pull requests govern source, contracts and construction artifacts.
GitHub review approval is code review, not independent scientific reproduction.
Reproduction records must name their human owners, environments, locked inputs,
artifact hashes and verdict commitments through the Factory protocol.

The `main` branch represents the current construction snapshot. Tagged releases
identify immutable public snapshots; they do not imply that every station is
live or that every included experiment is correct.

## Roles

- **Contributor:** proposes construction, methods, candidates or negative work.
- **Maintainer:** reviews repository integrity, scope and governance compliance.
- **Validator:** independently runs a locked scientific claim under their own
  human ownership. The claim author cannot be a validator.
- **Reviewer:** diagnoses disagreements and records the first material divergence.
- **Evaluator operator:** maintains sealed inputs and returns bounded verdicts.

One person may hold several general roles, but never author and validator on the
same claim, and never both required validator identities.

## Changing governance

Governance changes require a dedicated pull request that names the affected
invariants and migration consequences. A workbench contribution must not weaken
global governance as a side effect.

