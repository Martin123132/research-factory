# Candidate research artifacts

This directory is the only repository intake boundary reserved for future
candidate research packages. It is currently closed because no workbench is
authorised for live research.

Two handling modes will be supported:

1. `OPEN_DEPOSIT` — the rightsholder chooses an approved SPDX licence, records
   the artifact hash and grants the permissions that licence states. Ownership
   remains with the contributor.
2. `METADATA_ONLY` — the repository stores only non-confidential factual
   metadata, provenance, hashes and permitted links. The protected artifact is
   not copied into Git.

Files placed here do not inherit Apache-2.0, CC-BY-4.0 or any other Factory
licence. Every deposited artifact will require its own machine-readable rights
declaration and licence information. Unclassified files fail the repository's
licensing check.

The existing `factory/workbenches/**/examples` files are Factory-authored
commissioning fixtures, not candidate intake. Future contributor research must
use this boundary once its intake controls are opened.

Do not upload confidential or potentially patent-sensitive material. A pull
request, issue, hash record or metadata description is still a public
disclosure when the repository is public.
