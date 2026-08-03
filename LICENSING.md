# Licensing plan and current status

Status: **no repository-wide licence is active**.

The absence of a `LICENSE` file is deliberate while this framework is reviewed.
Under default copyright, publishing a GitHub repository does not automatically
give everyone permission to reproduce, modify or redistribute its contents.
Repository visibility and licensing are separate decisions.

This means the repository should remain private during the current policy
review, and outside substantive contributions should not be merged without a
clear written rights basis.

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

## Proposed path-specific model

Subject to rights audit and legal review:

| Material | Proposed treatment |
| --- | --- |
| Factory infrastructure and evaluator code | Apache License 2.0 |
| Factory-authored documentation and diagrams | Creative Commons Attribution 4.0 |
| Factory-authored factual metadata and public-domain-ready records | CC0 1.0 dedication where legally possible |
| Third-party assets | Their upstream licence; never silently relicensed |
| Candidate research artifacts | Per-artifact licence plus the minimum explicit permission needed to store, reproduce, validate and publish the evidence record |
| Names, logos and marks | Reserved; no implied trade-mark licence |

Apache 2.0 contains an express patent grant for certain contributor patent
claims necessarily infringed by a contribution. That is useful for Factory
infrastructure but may be inappropriate as an automatic blanket licence for
every research candidate. Candidate artifacts therefore need a deliberate
choice rather than accidental inheritance.

## Activation checklist

Before adding operative licence files:

1. identify the rightsholder for every existing path;
2. audit third-party code, data, fonts, media and generated assets;
3. define exact path boundaries and precedence rules;
4. draft the narrow research-deposit permission with qualified legal advice;
5. decide whether candidate artifacts must be open, may be evaluation-only, or
   may choose from an approved licence list;
6. add full standard licence texts, SPDX identifiers and notices;
7. obtain consent for any existing material being relicensed; and
8. enable contributor sign-off only after those licences exist.

No maintainer can relicense another person's contribution merely by merging a
policy pull request.

References:

- [GitHub: Licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html)
- [UK IPO: Licensing intellectual property](https://www.gov.uk/guidance/licensing-intellectual-property)
