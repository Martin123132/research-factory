# Offline release and recovery

The public Git repository is the durable Factory. The hosted Hangar is an
optional view and is not required to inspect stations, run entry gates, verify
contracts or recover the construction history.

## Build a recovery package

Start from a clean checkout and write the package under the ignored `work/`
directory or to an external drive:

```powershell
python factory/release/build_offline_release.py `
  --ref HEAD `
  --output work/offline-release

python factory/release/verify_offline_release.py work/offline-release
```

The output contains exactly three files:

- a tar archive of files tracked at the recorded commit;
- a Git bundle containing the selected ref's recoverable history and tags; and
- a closed manifest containing the commit, byte sizes and SHA-256 values.

The bundle intentionally excludes ignored local ledgers, private evaluator
state, credentials, hosted runtime state and hidden material. It has no
scientific standing.

## Recover without GitHub or the Hangar

Verify the directory before extracting or cloning it. Then either restore the
tracked source snapshot:

```powershell
New-Item -ItemType Directory recovered-source
tar -xf work/offline-release/research-factory-source-*.tar -C recovered-source
```

or restore the Git history:

```powershell
git clone work/offline-release/research-factory-history-*.bundle recovered-history
git -C recovered-history switch -c main
```

The bundle clone starts at the manifest's exact commit. Creating `main` gives
the detached recovery checkout a normal local branch without claiming that a
remote service exists.

After recovery, install the locked dependencies and verify the local engine:

```powershell
python -m venv factory/.venv
factory/.venv/Scripts/python.exe -m pip install -r factory/requirements.lock
factory/.venv/Scripts/python.exe factory/enginectl.py doctor
```

On Linux or macOS, use `factory/.venv/bin/python` instead.

## Publication rule

When a package is copied to removable storage or attached to a release, retain
all three files together. Record or sign the manifest's own SHA-256 in a second
location so corruption or replacement of the whole directory can be detected.
Never add evaluator secrets or private scientific work to make an offline
package appear more complete.
