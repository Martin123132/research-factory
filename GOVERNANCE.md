# Research Factory governance

## Purpose

The Factory coordinates human-owned agents around measurable research problems.
Authority comes from reproducible evidence, not credentials, reputation or the
fluency of a generated explanation.

The [`OPEN_FACTORY_CHARTER.md`](OPEN_FACTORY_CHARTER.md) is the constitutional
worker, rights and operating boundary. The
[`FACTORY_QUALITY_STANDARD.md`](FACTORY_QUALITY_STANDARD.md) makes that boundary
measurable without allowing strength in one domain to compensate for failure in
another.

## Non-negotiable rules

1. Every station defines its input population, required output, independent
   verifier, hard gates, score and practical guardrail before live work.
2. Hard gates fail closed. A better score cannot cancel invalid output, missing
   evidence, a timeout, a safety failure or a verifier error.
3. Tolerances are task-specific. Exact bytes, hashes, logical claims and integer
   accounting use zero tolerance. Statistical work declares seeds, repetitions,
   aggregation, confidence and runner class.
4. The author cannot reproduce their own claim. Promotion requires two other,
   distinct accountable humans and neither person may occupy both validator
   roles.
5. Validators commit their evidence and conclusion before the hidden claim is
   revealed. A deterministic disagreement opens diagnosis and human review; a
   third run cannot promote by majority vote.
6. Negative, invalid, disputed and unrunable work remains searchable so future
   workers do not unknowingly repeat the same search.
7. No local runner, agent, pull request, site administrator or repository owner
   can grant scientific standing outside the recorded promotion process.
8. The Factory does not acquire contributor ownership. Rights, inventorship,
   credit and external prizes remain separate from scientific scoring.
9. No confidential or patent-sensitive invention may be uploaded. A rights
   declaration is required but is never treated as legal clearance by the
   Factory.
10. Every dispatched human or agent workload must declare its scope, resource
    ceiling, stop conditions, evidence class and accountable human before work.
11. People may pause or leave without losing earned attribution. Attempt count,
    compute use and shift length cannot substitute for evidence quality.
12. Factory-quality claims must cite the exact standard and hash-bound evidence;
    self-assessment can never call itself an independent audit.
13. A material correction changes current standing only through the universal
    append-only correction record. Original bytes and earlier standing remain
    visible; terminal retractions, invalidations and supersessions cannot be
    silently restored.
14. No new agent runner receives Factory process-execution authority unless a
    hash-bound dispatch budget passes every enforcement dimension. Partial
    monitoring produces a rejection ticket; an agent cannot expand its own
    scope, interfaces, data access, spending, duration or evidence class.
15. A final procedural appeal record requires two or more distinct named
    reviewers who are neither the requester nor named materially involved
    authors, validators or reviewers. Their committed evidence hashes must be
    distinct. A split returns to diagnosis; it cannot change standing by
    majority vote, and any correction still requires its own append-only record.

## Repository authority

GitHub pull requests govern source, contracts and construction artifacts.
GitHub review approval is code review, not independent scientific reproduction.
Reproduction records must name their accountable humans, environments, locked inputs,
artifact hashes and verdict commitments through the Factory protocol.

The `main` branch represents the current construction snapshot. Tagged releases
identify immutable public snapshots; they do not imply that every station is
live or that every included experiment is correct.

## Roles

- **Contributor:** proposes construction, methods, candidates or negative work.
- **Maintainer:** reviews repository integrity, scope and governance compliance.
- **Validator:** independently runs a locked scientific claim under their own
  accountable identity. The claim author cannot be a validator.
- **Reviewer:** diagnoses disagreements and records the first material divergence.
- **Appeal reviewer:** records a conflict declaration and a bounded procedural
  finding; cannot decide an appeal they requested or materially participated in.
- **Evaluator operator:** maintains sealed inputs and returns bounded verdicts.

One person may hold several general roles, but never author and validator on the
same claim, never both required validator identities, and never appeal reviewer
and materially involved party on the same appeal.

## Rights, credit and commercial neutrality

Contributors retain the rights they lawfully hold and do not assign them to the
Factory. Every substantive package must include the declaration in
[`CONTRIBUTOR_TERMS.md`](CONTRIBUTOR_TERMS.md). Maintainers record provenance;
they do not certify ownership, inventorship, patentability or freedom to
operate.

Scientific promotion cannot depend on a patent position, commercial licence,
prize agreement or adoption of the voluntary Progress-Friendly Patent Pledge.
A specific safety or rights dispute may quarantine distribution while it is
investigated, but it cannot be used to alter a measurement or manufacture a
scientific pass.

The controlling boundaries are documented in
[`IP_POLICY.md`](IP_POLICY.md),
[`PATENTS_AND_PUBLIC_DISCLOSURE.md`](PATENTS_AND_PUBLIC_DISCLOSURE.md),
[`CREDIT_AUTHORSHIP_AND_PRIZES.md`](CREDIT_AUTHORSHIP_AND_PRIZES.md) and
[`BREAKTHROUGH_PROTOCOL.md`](BREAKTHROUGH_PROTOCOL.md).

The non-commercial scientific boundary does not prevent contributors from
working elsewhere or using compatible commercial tools. It prevents funding,
provider choice, investment and commercial terms from changing evidence gates.

## Changing governance

Governance changes require a dedicated pull request that names the affected
invariants and migration consequences. A workbench contribution must not weaken
global governance as a side effect.

Changes to the Open Factory Charter or quality controls must state whether any
worker right, evidence invariant or appeal protection is weakened and must
refresh the evidence-bound current assessment.

Changes that activate or broaden a licence require an explicit rights audit and
must not be bundled into an unrelated governance or scientific contribution.
