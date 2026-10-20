# Development dependency security

Maintenance record: 2026-10-20. This is infrastructure maintenance, not scientific
validation or a security certification.

The previous 15 npm warning entries represented three underlying advisories.
Production dependencies were already clear. Two published fixes are pinned:

- `fflate` 0.7.5 replaces 0.7.3, fixing
  [malformed ZIP64 archive handling](https://github.com/advisories/GHSA-px8p-9vwx-vf98).
  The override stays within the existing 0.7 release line used by font/OG tooling.
- Only `@esbuild-kit/core-utils`'s old esbuild is overridden to 0.25.12, matching
  Drizzle Kit's already installed supported release line and fixing the
  [development server CORS issue](https://github.com/advisories/GHSA-67mh-4wv8-2f99).
  Other esbuild consumers retain their own versions.

## Temporary braces mitigation, not an upstream fix

[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
affects `braces` 3.0.3. As of this maintenance record there is no published fixed
release; the [upstream discussion](https://github.com/micromatch/braces/issues/70)
is open. Eight affected entries are this one advisory propagating through
micromatch, fast-glob, Next lint tooling and Vinext's CommonJS tooling.

`scripts/guard-braces.mjs` adds a local parser guard before creating a nested AST
node. It rejects brace **and parenthesis** nesting beyond 100 with a controlled
`SyntaxError`, before recursive compilation, expansion or invalid-input cleanup.
The normal parser still handles escaping, quoted literals and character classes.
This does not make arbitrary regular expressions or expansion sizes safe. The
tools must only process trusted project configuration; do not expose them as a
service for untrusted glob patterns or accept caller-supplied AST objects.

The installer verifies the entire upstream parser's SHA-256 and exact package
version before changing it, handles every locked copy, and is idempotent. Unknown
source bytes or a changed version fail closed for manual review. It preserves
the upstream MIT licence, package identity and version. Only installed
`node_modules` is patched; no third-party source is vendored or relicensed.

**Raw `npm audit` still reports eight high-severity entries. Do not describe this
as zero vulnerabilities or an upstream resolution.** `npm run security:audit`
prints the counts and accepts only this exact advisory after verifying every
installed parser guard. Any other advisory, unknown dependency chain, malformed
audit response or missing guard fails the gate. The existing production audit
remains unchanged. CI runs both gates.

## Installation, checks and retirement

Use `npm ci`, which runs the guarded postinstall. If lifecycle scripts are
disabled, run `npm run postinstall` explicitly. `npm run security:verify`, and
the development/build/lint pre-hooks, reject missing or modified guards.

Run `npm run security:audit`, typecheck, lint and `npm test`. Regression coverage
includes normal glob expansion and matching, deep patterns, guard integrity,
audit rejection, ZIP round-trips/malformed ZIP64 input, font/OG rendering,
Drizzle schema generation and the old loader's esbuild transform interface.
Potentially hanging input tests run in bounded child processes.

When upstream publishes a fixed release, review its change, upgrade the lock,
remove the local parser patch and advisory exception, retain regression tests
and require an unqualified full npm audit. Do not delete the current guard merely
to silence an installer error after a dependency update. Revisit the scoped
esbuild and fflate overrides when their parents adopt fixed versions themselves.
