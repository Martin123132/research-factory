# Key-person recovery drill

This drill tests the *technical* part of a handover: a maintainer starts from a
verified offline release, recovers its Git history into a normal local branch,
removes the bundle origin, checks object integrity and proves the recovered
checkout is clean.

It intentionally does **not** claim that a maintainer is independent, that two
people have participated, that anyone has inherited a hosted account, or that
[`RESILIENCE-04`](../quality/factory-quality-standard-v1.json) is met. Those are
human facts that need real, reviewable observations. A report records them as
unproven, even when its technical recovery checks pass.

## Run it

First build and verify an offline release as described in
[`OFFLINE_RECOVERY.md`](../../OFFLINE_RECOVERY.md). Then, from `factory/`:

```powershell
.\.venv\Scripts\python.exe -m recovery.run_key_person_recovery_drill `
  --release ..\work\offline-release `
  --output state\key-person-recovery-001 `
  --operator-id human:second-maintainer `
  --display-name "Second Maintainer"

.\.venv\Scripts\python.exe -m recovery.verify_key_person_recovery_drill `
  --release ..\work\offline-release `
  state\key-person-recovery-001
```

The output contains only a hash-bound public report. The recovered working copy
is disposable and never receives a hosted remote, credentials, scientific
authority or permission to alter a live result.

## Turning a drill into a real resilience observation

Ask a second maintainer to perform this independently, record the evidence in a
dedicated reviewable change, and have reviewers check the actual people,
absence of the founder, recovery conditions and any critical administration
performed. Only that later human observation can support updating the quality
assessment. The tool cannot certify it for itself.
