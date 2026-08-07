# Factory Quality Standard v1.0

The Factory Quality Standard measures whether a scientific workshop is fair,
reproducible, useful and resilient. It measures the factory, not how impressive
its research claims sound.

The normative control catalogue is
[`factory/quality/factory-quality-standard-v1.json`](factory/quality/factory-quality-standard-v1.json).
The dated self-assessment is
[`factory/quality/current-assessment.json`](factory/quality/current-assessment.json).

## Non-compensating gates

There is no aggregate quality score. A factory cannot compensate for stolen
credit with fast runners, unsafe workloads with open source, or answer leakage
with a high replication rate. Each mandatory control reports one outcome:

- `MEETS`: the available evidence satisfies the control at or above its minimum
  evidence level;
- `PARTIAL`: a real mechanism exists, but a stated gap prevents conformance; or
- `BLOCKED`: the mechanism or evidence does not yet exist.

Every `PARTIAL` or `BLOCKED` result must state its limitation. A profile with
any such result is not operationally certified.

## Evidence ladder

Evidence levels are cumulative and ordered:

1. `NONE` — no admissible evidence;
2. `DECLARED` — a public, versioned policy or contract states the rule;
3. `ENFORCED` — code, schema, permissions or automated tests fail when the rule
   is broken;
4. `OBSERVED` — an actual bounded operation produced a retained record showing
   the mechanism worked; and
5. `INDEPENDENTLY_AUDITED` — a conflict-free external person or organisation
   checked the evidence and published a signed or otherwise verifiable finding.

A self-authored policy cannot be relabelled as an independent audit. A
synthetic fixture may demonstrate enforcement but does not prove live
scientific operation.

## Seven quality domains

### 1. Open access

The core path is free, credential-neutral, accessible and privacy-preserving.
Reasonable safety, rights and independence checks may be required, but they
must be proportionate and published.

### 2. Working conditions

Work has bounded scope, resources and stop conditions. Humans can pause or
leave without retaliation, retain earned attribution and control the authority
and budget of their agents. Raw output volume is not a quality proxy.

### 3. Scientific integrity

Gates and tolerances are declared before evaluation. Claims are blind-tested,
the author cannot self-validate, two validators mean two other humans, and a
split result opens diagnosis rather than a vote.

### 4. Useful memory

Progress, no-gain, blocked, unrunnable, disputed and corrected work remains
traceable. Public search exposes bounded metadata and hashes rather than hidden
or personal evidence.

### 5. Rights and credit

The factory does not take ownership. Credit follows recorded roles. Patents,
prizes, funding and commercial decisions cannot change scientific gates.
Material support, provider subsidies and decision conflicts have an
append-only public disclosure route. Conflicts and appeals have an accountable
route.

### 6. Resilience and portability

The factory is provider-neutral, evidence is portable and hash-bound, and a
verified recovery path exists. Mature operation must also survive loss of a
founder or sole maintainer.

### 7. Transparent governance

Controls and assessments are machine-readable and evidence-bound. Material
sponsors, compute subsidies and conflicts are disclosed. The highest profile
requires an independent audit rather than self-certification.

## Profiles and certification language

- `FOUNDATION_ONLY`: policies and construction mechanisms exist, but gaps or a
  lack of real operation prevent certification.
- `OPERATIONALLY_CONFORMANT`: every mandatory control is `MEETS`, required
  operational controls have `OBSERVED` evidence, and no critical exception is
  open.
- `SCIENTIFICALLY_DEMONSTRATED`: operational conformance plus at least one live,
  blind claim processed through two genuinely independent human reproductions
  with its complete evidence and dispute route retained.
- `INDEPENDENTLY_AUDITED`: scientific demonstration plus a current,
  conflict-free external audit of the complete profile.

Only the last three names are certifications. `FOUNDATION_ONLY` is a truthful
construction status, not a bronze award.

## Anti-gaming rules

An assessment must:

- include every control from exactly one standard version in canonical order;
- bind the exact standard and every evidence file with SHA-256;
- reject duplicate keys, missing controls, unsafe paths and changed evidence;
- derive its outcome counts rather than accepting a decorative total;
- keep operational, scientific and independent-audit certification false when
  prerequisites are absent;
- state zero live stations when the public station contracts say zero; and
- be regenerated when cited evidence changes.

Breakthrough count, publication count, investment, employee pedigree, model
size and social attention are deliberately not quality controls.

## Current boundary

The initial assessment is `FOUNDATION_ONLY`. It records strong machine-enforced
construction in several domains while publishing the unfinished process-grade
worker-budget adapter, bus-factor and independent-audit controls.
Its conflict-independent appeal record is closed, append-only and synthetically
enforced, but identity records still do not prove distinct real people. Its universal
correction and retraction record is closed and synthetically enforced, but no
live correction has yet been required.
Blind and two-human rules exist structurally, but the Factory has not onboarded
the required independent people or authorised a live station.

Run the verifier from the repository root:

```powershell
python factory/quality/verify_quality.py
python factory/enginectl.py quality
```

Passing these commands proves that the assessment matches its declared public
evidence. It does not upgrade the evidence to `OBSERVED`, certify the Factory or
turn construction into science.
