# Public material-support disclosures

This is a small, local, append-only ledger for public declarations of material
support that could bear on a Factory workbench or governance decision. It is
for facts such as funding, compute credits, provider subsidies, donated data or
materials, employment, institutional ties and governance interests.

It is deliberately **not** a scientific-results system. Every record locks the
following boundary:

- scientific gates, measurements and promotion remain unchanged;
- identity records do not prove authority or validator independence;
- the ledger does not give legal clearance, settle ownership or validate a
  claim;
- a declaration, amendment or end record cannot be silently rewritten.

Do not place private contracts, account tokens, personal contact details,
sealed inputs, grant applications or unpublished financial documents in this
public ledger. Record only a factual public description and disclose at the
affected Factory, workbench or governance-decision scope.

## Use it locally

From [`factory/`](..):

```powershell
.\.venv\Scripts\python.exe enginectl.py support-append `
  --ledger state\public\support-disclosures.jsonl `
  --draft disclosures\support-disclosure.example.json

.\.venv\Scripts\python.exe enginectl.py support-verify `
  --ledger state\public\support-disclosures.jsonl

.\.venv\Scripts\python.exe enginectl.py support-history `
  --ledger state\public\support-disclosures.jsonl `
  --scope-id research-factory
```

Use `DECLARE` to open a relationship, `AMEND` when a public disclosure has
materially changed, and `END` when it has ended. An end remains visible and is
terminal in v1; a later relationship uses a new disclosure ID.

## Commissioning proof

The synthetic drill declares and ends a fictional compute credit, exports its
public index, then verifies the chained ledger and its no-influence boundary.
It creates no live claim, scientific standing or promotion eligibility.

```powershell
.\.venv\Scripts\python.exe -m disclosures.run_synthetic_drill `
  --output state\support-disclosure-synthetic-001

.\.venv\Scripts\python.exe -m disclosures.verify_synthetic_drill `
  state\support-disclosure-synthetic-001
```
