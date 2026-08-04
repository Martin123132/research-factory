# Security policy

## Never commit

- hidden benchmarks, holdouts or answer sheets;
- source-repository, cloud, model-provider or deployment credentials;
- `.env` files, private keys or session tokens;
- unredacted human identity evidence;
- private evaluator logs that reveal sealed results.

The repository ignore rules are a backstop, not an authorization boundary.
Inspect staged files before every commit.

## Public-history scanning

CI downloads Gitleaks v8.30.1 from its official release, verifies the archive's
SHA-256 checksum and scans the complete reachable Git history. The
`.gitleaksignore` file contains exactly two reviewed fingerprints for synthetic
commissioning tokens. It contains no wildcard, path-wide or rule-wide
exceptions. A new finding must be investigated; do not silence it merely to
make CI pass.

Removing a secret in a later commit does not remove it from history. If a real
credential is ever committed, revoke it first, preserve incident evidence
privately and then follow GitHub's sensitive-data removal procedure.

The Hangar CI gate also audits deployable npm dependencies and currently finds
zero advisories. As of 2026-08-04, a full development-tree audit separately
reports four moderate advisories inherited through Drizzle Kit's deprecated
`@esbuild-kit` loader. npm's offered remedy is a breaking Drizzle Kit downgrade,
so it has not been applied. Drizzle Kit is restricted to trusted, local schema
generation; it is not installed as deployable application code. Dependabot
remains enabled so the upstream replacement can be adopted when available.

## Runner boundary

The current trusted-local runners execute only source already trusted by the
operator. Process timeouts, output caps and process-tree cleanup are not a
sandbox. They do not enforce network isolation, read-only filesystems, verified
identity, energy accounting or promotion-grade attestation.

Arbitrary public code must run only in a disposable evaluator host with no
network, read-only inputs, bounded resources and a separately authenticated
result channel.

## Reporting a vulnerability

Do not publish an exploit, credential or holdout leak in a normal issue. Use a
private GitHub security advisory when available, or contact the repository owner
privately through their GitHub profile. Include the affected component, impact,
reproduction conditions and the minimum evidence needed to confirm the report.
