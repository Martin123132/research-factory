# Factory quality profile

This directory turns the Open Factory Charter into non-compensating,
machine-readable gates. It contains:

- `factory-quality-standard-v1.json`: the normative 28-control catalogue;
- `factory-quality-standard-v1.schema.json`: its closed JSON Schema;
- `current-assessment.json`: the dated evidence-bound Factory assessment;
- `factory-quality-assessment-v1.schema.json`: the closed assessment shape; and
- `verify_quality.py`: the fail-closed verifier.

Run from the repository root:

```powershell
python factory/quality/verify_quality.py
python -m unittest discover -s factory/quality/tests -p "test_*.py" -v
python factory/enginectl.py quality --json
```

The verifier checks all 28 controls in canonical order, exact standard bytes,
every cited evidence hash, current public station readiness, derived outcome
counts, certification prerequisites and the Hangar's derived public summary.

Passing verifies the honesty and integrity of the assessment. It does not turn
`PARTIAL` or `BLOCKED` controls into passes and does not certify live science.
