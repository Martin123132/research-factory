# Commissioning adapters

This directory is the allowlisted bridge between the 100 catalogue briefs and
station-specific scientific contracts.

- `index.json` is a self-hashed registry. An override not listed there cannot
  affect generated contracts.
- Each override is closed-schema data and cannot set governance, readiness,
  live authority, scientific credit or promotion state.
- An adapter copies named scientific fields, verifies every declared asset,
  and derives readiness fail-closed.
- `DIGITAL_COMPRESSION_V1` covers exact restoration on one fixed public corpus.
  It is not a universal compression scorer: CRAM, lossy scientific arrays,
  perceptual codecs and stateful deduplication require different adapters.
- `DIGITAL_OPTIMIZATION_V1` is a closed combinatorial-optimisation family. Its
  first and only enabled plugin is `SYMMETRIC_TSP_V1`; other route, scheduling,
  graph and TSPLIB problem types require explicitly reviewed plugins.

Changing adapter code or the registry changes the generator identity. Changing
a station override or one of its locked assets changes that station's contract
and kit digest.
