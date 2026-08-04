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

- [ ] Repository owner has explicitly accepted publication of the author and
  committer email already stored in reachable Git history, or has chosen a
  sanitized fresh-history repository instead.

## Immediately after publication

- [ ] Confirm an unauthenticated clean clone succeeds.
- [ ] Confirm verification passes from that clean clone.
- [ ] Protect `main`: require pull requests, conversation resolution and all
  four verification jobs; block force pushes and deletion.
- [ ] Enable vulnerability alerts, automated security fixes, private
  vulnerability reporting and available secret-scanning protections.
- [ ] Confirm the public repository exposes no hidden evaluator or private
  Hangar data.

## Still deliberately closed

- Candidate scientific artifact deposit.
- Public reproduction verdict submission.
- Live evaluator dispatch.
- Hidden-answer reveal.
- Scientific promotion.
- Public access to the hosted Hangar.

These remain closed until their own threat model, evaluator isolation and
governance gates are implemented and reviewed.
