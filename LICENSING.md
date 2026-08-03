# Licensing plan and current status

Status: **path-scoped standard licences are active; no repository-wide blanket
licence exists**.

[`REUSE.toml`](REUSE.toml) is the authoritative machine-readable map and
[`LICENSE.md`](LICENSE.md) is the human summary. Every tracked file is assigned
an established SPDX licence, or is one of the licence/REUSE control files that
the REUSE specification excludes from coverage. CI fails when a new tracked
file has no classification.

Repository visibility and licensing remain separate decisions. Making the
repository public does not open live scientific intake: it opens only the
classified construction materials and contribution route described below.

## Why one blanket licence is unsuitable

The repository contains different kinds of material:

- Factory infrastructure and evaluator software;
- explanatory documentation and diagrams;
- factual catalogues, measurements and provenance metadata;
- third-party datasets and tools with their own terms; and
- research candidates that may have separate copyright and patent interests.

A software licence over the entire tree could accidentally grant permissions
for research artifacts that their rightsholders did not intend. Conversely, an
evaluation-only rule over the whole tree would prevent useful open-source
development of the Factory itself.

## Active path-specific model

| Material | Treatment |
| --- | --- |
| Factory infrastructure and evaluator code | Apache License 2.0 |
| Factory-authored documentation and diagrams | Creative Commons Attribution 4.0 |
| Factory-authored factual metadata and public-domain-ready records | CC0 1.0 dedication where legally possible |
| Third-party assets | Their upstream licence; never silently relicensed |
| Candidate research artifacts | Per-artifact approved licence or metadata-only; never inherited from the surrounding repository |
| Names, logos and marks | Reserved; no implied trade-mark licence |

Apache 2.0 contains an express patent grant for certain contributor patent
claims necessarily infringed by a contribution. That is useful for Factory
infrastructure but may be inappropriate as an automatic blanket licence for
every research candidate. Candidate artifacts therefore need a deliberate
choice rather than accidental inheritance.

## No paid-advice entry gate

Building, testing and contributing to the Factory must not depend on anyone
being able to pay a lawyer or patent attorney. In particular:

- no contributor is required to buy legal advice to open a workbench, run an
  experiment, validate a result or receive scientific credit;
- the Factory should use established, unmodified standard licences instead of
  inventing bespoke legal language wherever possible;
- a candidate that cannot yet be shared under an approved standard licence can
  remain private, or the public record can contain only non-confidential factual
  metadata, provenance, hashes and permitted links rather than ingesting the
  protected artifact; and
- free official tools, IP clinics and introductory consultations can be used
  for early guidance.

Paid professional help is an optional decision for the relevant rightsholder
when a concrete high-value event exists, such as filing a patent, negotiating a
commercial transaction, resolving complex joint ownership or handling a
dispute. It is not a Factory membership cost or a condition of scientific
acceptance.

## Classification checklist

Before adding or moving a tracked file:

1. identify the contributor or upstream rightsholder;
2. record third-party source, version, licence and required notice;
3. place the path in the correct `REUSE.toml` class or add file-local SPDX
   information;
4. keep candidate artifacts inside the dedicated intake boundary and choose
   `OPEN_DEPOSIT` or `METADATA_ONLY`;
5. run `reuse lint`; and
6. update provenance records when media, datasets or generated artifacts change.

No maintainer can relicense another person's contribution merely by changing a
path rule. Moving an existing contribution into a different licence class
requires the rightsholder's permission.

References:

- [GitHub: Licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html)
- [UK IPO: Licensing intellectual property](https://www.gov.uk/guidance/licensing-intellectual-property)
- [UK IPO: free advice and PatLib centres](https://www.gov.uk/guidance/seeking-intellectual-property-advice)
- [UK IPO: free CIPA IP Clinics](https://www.gov.uk/guidance/get-legal-advice-from-an-intellectual-property-professional)
