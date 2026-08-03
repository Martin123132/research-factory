# Contributor declaration

Status: **draft; activation depends on the licensing decision in
[LICENSING.md](LICENSING.md)**.

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

Before the licence framework is activated, external substantive contributions
must not be merged merely because a pull request is technically valid. Default
copyright applies unless an explicit licence or written permission says
otherwise. Construction-only review can continue in the private repository.

After activation, each accepted artifact must have an unambiguous licence class.
An unlabeled research artifact fails closed rather than inheriting a guessed
licence from a neighbouring file.

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

## Future sign-off

When the repository's path-specific licences are activated, maintainers should
consider adopting the
[Developer Certificate of Origin 1.1](https://developercertificate.org/) with
`Signed-off-by` commits. It should not be activated before the repository has
the open-source licence referenced by that certificate.
