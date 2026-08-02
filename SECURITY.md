# Security policy

## Never commit

- hidden benchmarks, holdouts or answer sheets;
- source-repository, cloud, model-provider or deployment credentials;
- `.env` files, private keys or session tokens;
- unredacted human identity evidence;
- private evaluator logs that reveal sealed results.

The repository ignore rules are a backstop, not an authorization boundary.
Inspect staged files before every commit.

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

