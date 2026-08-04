# Public launch checklist

This checklist separates repository publication from scientific activation.
Publishing the construction source does not open candidate intake, expose sealed
evaluation material, make the Hangar public or create a live-research station.

## Completed before publication

- [x] Repository history and tracked files reviewed for credentials, private
  keys, hidden holdouts, private datasets and local filesystem paths.
- [x] Full-history Gitleaks v8.30.1 scan completed on 2026-08-04 across the 13
  commits then present.
- [x] Two synthetic commissioning tokens identified and reviewed. Their exact
  fingerprints, but not wildcard rules, are the complete `.gitleaksignore`
  baseline.
- [x] Every tracked path has an explicit REUSE licence classification.
- [x] Every tracked media file has a declared origin, licence and SHA-256 hash.
- [x] Deployable Hangar dependencies have zero npm audit advisories; the
  separately documented development-only Drizzle Kit advisory is not shipped.
- [x] Locked Python dependencies have zero known advisories under the pinned
  `pip-audit` gate.
- [x] Blank issues and public scientific-reproduction intake are disabled.
- [x] Candidate artifact intake contains only its closed-boundary README.
- [x] All 100 stations are construction-only: 99 `CONTRACT_DRAFT`, one
  `COMMISSIONING_READY`, and zero live-research stations.
- [x] The hosted Hangar remains a separate private deployment.

## Manual publication decision

- [x] Repository owner explicitly accepted publication of the author and
  committer email already stored in reachable Git history by publishing the
  repository on 2026-08-04.

## Immediately after publication

- [x] An unauthenticated HTTPS clone with credential helpers disabled succeeded
  at public commit `d5df885c0269cd16d75ac7820c8718f7edf7b347`.
- [x] The full published verification sequence passed from that clean clone on
  Python 3.13.13 and Node 24.15.0 with npm 11.12.1.
- [x] `main` requires pull requests, the latest base, conversation resolution,
  linear history and all four verification jobs; force pushes and deletion are
  blocked. Zero approvals and administrator bypass preserve the documented
  sole-maintainer recovery path until another maintainer joins.
- [x] Vulnerability alerts, automated security fixes, Dependabot security
  updates, private vulnerability reporting, secret scanning and push
  protection are enabled. GitHub Actions defaults to read-only permissions and
  cannot approve pull requests.
- [x] The public-boundary verifier passed across 2,058 tracked paths and the
  provenance verifier accounted for all 16 tracked media files; no hidden
  evaluator or private Hangar data is exposed.

## Still deliberately closed

- Candidate scientific artifact deposit.
- Public reproduction verdict submission.
- Live evaluator dispatch.
- Hidden-answer reveal.
- Scientific promotion.
- Public access to the hosted Hangar.

These remain closed until their own threat model, evaluator isolation and
governance gates are implemented and reviewed.
