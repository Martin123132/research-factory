# Contributor declaration

Status: **active for classified construction contributions**. Candidate
scientific artifacts remain closed until a live workbench and per-artifact
intake are explicitly enabled.

The Factory does not require contributors to assign ownership. It does require
an accountable human to make a truthful provenance and rights declaration for
every substantive package.

## Declaration

By submitting a substantive contribution, the accountable human declares that,
to the best of their knowledge after reasonable checks:

1. they created the contribution, received it from a recorded source, or are
   otherwise authorised to submit it;
2. every material dependency and third-party component is identified with its
   source, version and licence or permission;
3. they have checked relevant employment, university, funding, collaboration
   and prior contractual obligations;
4. they have named material human contributors and declared material AI use;
5. the package is intended for a public, indefinitely retained research record
   and contains no secret, credential, personal data, embargoed material or
   confidential invention;
6. any relevant patent step occurred before public submission, or the declared
   patent intent is `NONE` or `OPEN_COMMONS`;
7. possible joint authors, joint inventors and other rightsholders have not been
   knowingly omitted; and
8. the contribution may be handled only under the licences expressly identified
   for its paths and artifacts.

The declaration is not a warranty by the Factory and does not transfer the
contributor's ownership to it.

## Repository acceptance

Each accepted construction artifact must have the unambiguous licence class
assigned by [`REUSE.toml`](REUSE.toml). By intentionally submitting material
for inclusion in a classified path, the contributor offers that contribution
under the licence assigned to that path. Copyright ownership is not assigned.

An unlabeled research artifact fails closed rather than inheriting a guessed
licence from a neighbouring file. Future research candidates use the separate
[`candidate_artifacts/`](candidate_artifacts/) boundary; it is currently closed
to artifact deposits.

## Machine-readable declaration

The station submission schemas enforce the shape and allowed vocabulary of the
rights declaration and contribution ledger. Schema validity means only that the
questions were answered in the required form; it does not prove that an answer
is legally correct or decide authorship, inventorship or prize entitlement.

## Corrections and withdrawal

A contributor must promptly report a material error in their declaration.
Maintainers may stop distribution, quarantine a package and append a correction
or retraction. Public hashes, citations and already distributed copies may make
complete erasure impossible, so contributors must review before submission.
The closed record and terminal standing rules are defined in
[`factory/corrections/`](factory/corrections/README.md). A record preserves the
original bytes, identifies the asserted authority and conflict, and links any
replacement by SHA-256. Schema validity does not prove legal authority.

## Contributor sign-off

Construction commits use a `Signed-off-by` trailer created with `git commit -s`.
The sign-off certifies the
[Developer Certificate of Origin 1.1](https://developercertificate.org/): the
contributor created the work or has the right to submit it under the applicable
path licence, and understands that the contribution and sign-off are public.
It is a provenance certificate, not a copyright assignment.
