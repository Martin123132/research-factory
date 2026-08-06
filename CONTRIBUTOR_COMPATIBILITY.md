# Contributor quickstart compatibility record

## Scope and evidence boundary

- Run date: 2026-08-06 (Europe/London).
- Repository: `https://github.com/Martin123132/research-factory.git`.
- Source commit in both clean clones:
  `37ff0dd2efbffec31c31a651f02f6bd000e93263`.
- Procedure under test: `CONTRIBUTOR_QUICKSTART.md` at that commit.
- Scope: `FACTORY-WIDE / HANGAR_CONSTRUCTION` only. No scientific
  benchmark, candidate, reproduction or promotion work was run.
- Operator qualification: the Windows and Linux runs used separate clean
  clones and separate operating environments, but both were operated by the
  same construction worker. This is not evidence of two independent humans.
- Durations are elapsed wall-clock milliseconds measured around each process.
  Linux durations include the small `docker exec` startup overhead.
- The placeholder branch `your-name/bounded-task` was replaced with an
  issue-specific branch name in each environment.

## Environment A: Windows clean clone

- OS: Microsoft Windows 10 Home 10.0.19045, build 19045.
- Shell: Windows PowerShell 5.1.19041.6456.
- Clean-clone parent:
  `D:\Temp\research-factory-ct001-win-d1d1f3b40c884411bfdbf31b0dcee069`.

### Tool preflight

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `git --version` | `git version 2.54.0.windows.1` | 0 | 49 |
| `python --version` | `Python 3.13.13` | 0 | 35 |
| `node --version` | `v24.15.0` | 0 | 45 |
| `npm.cmd --version` | `11.12.1` | 0 | 497 |
| `reuse --version` | command not found | 1 | 86 |

### As-written quickstart and dependency check

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `git clone https://github.com/Martin123132/research-factory.git` | clean clone created | 0 | 4,027 |
| `cd research-factory` | working directory entered | 0 | 4 |
| `git switch -c ct001/windows-quickstart` | branch created | 0 | 81 |
| `reuse lint` | `reuse` was not installed | 1 | 83 |
| `python factory/workbench_standard/generate_station_kits.py --check` | 100 station kits verified | 0 | 9,647 |
| `python -m unittest discover -s factory/workbench_standard/tests -p "test_*.py" -v` | 39 tests passed | 0 | 3,260 |
| `python factory/enginectl.py doctor` | `ENGINE READY`; no hosted-provider dependency | 0 | 4,132 |
| `python -m unittest discover -s factory/engine/tests -t factory -p "test_*.py" -v` | 20 tests passed; one directory-symlink test skipped because the Windows account lacked symlink privilege | 0 | 31,327 |
| `cd factory/hangar` | working directory entered | 0 | 3 |
| `npm.cmd run typecheck` | `tsc` not found before dependency installation | 1 | 971 |
| `npm.cmd run lint` | `eslint` not found before dependency installation | 1 | 783 |
| `npm.cmd test` | catalogue and contract checks passed, then `vinext` was not found | 1 | 3,043 |

The quickstart does not tell a clean-clone contributor to install either the
locked Python/REUSE tools or the Hangar packages. The repository root README
does contain those setup commands. To distinguish missing setup from failing
project checks, the Hangar dependency step from the root README was then run:

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `npm.cmd ci` | 506 packages installed; npm reported four moderate-severity audit findings | 0 | 35,402 |
| `npm.cmd run typecheck` | passed | 0 | 5,335 |
| `npm.cmd run lint` | passed | 0 | 11,331 |
| `npm.cmd test` | build passed; 15 tests passed | 0 | 37,393 |
| `git status --short` | no tracked or untracked changes | 0 | 60 |

No generated station-kit file was hand-edited. `git status --short` was empty
after all commands, including `npm.cmd ci` and the Hangar build.

## Environment B: Debian Linux clean clone

- Container OS: Debian GNU/Linux 12 (bookworm).
- Kernel: Linux 6.6.114.1-microsoft-standard-WSL2, x86_64.
- Container image: `node:24-bookworm` at
  `sha256:934240a162082fd8b8a2f90cd5114446443f1eba1c5378f6687167ca405e6584`.
- Docker host: client 29.6.1, server 29.6.1.
- Clean clone: `/tmp/research-factory` inside a disposable container.

### Tool preflight

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `git --version` | `git version 2.39.5` | 0 | 171 |
| `python --version` | command not found | 127 | 186 |
| `python3 --version` | `Python 3.11.2` | 0 | 172 |
| `node --version` | `v24.19.0` | 0 | 184 |
| `npm --version` | `11.17.0` | 0 | 332 |
| `npm.cmd --version` | command not found | 127 | 182 |
| `reuse --version` | command not found | 127 | 186 |

### Commands exactly as printed in the PowerShell quickstart

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `git clone https://github.com/Martin123132/research-factory.git` | clean clone created | 0 | 2,770 |
| `cd research-factory` | working directory entered | 0 | 224 |
| `git switch -c ct001/linux-quickstart` | branch created | 0 | 197 |
| `reuse lint` | `reuse` not found | 127 | 162 |
| `python factory/workbench_standard/generate_station_kits.py --check` | `python` not found | 127 | 191 |
| `python -m unittest discover -s factory/workbench_standard/tests -p "test_*.py" -v` | `python` not found | 127 | 178 |
| `python factory/enginectl.py doctor` | `python` not found | 127 | 258 |
| `python -m unittest discover -s factory/engine/tests -t factory -p "test_*.py" -v` | `python` not found | 127 | 177 |
| `cd factory/hangar` | working directory entered | 0 | 208 |
| `npm.cmd run typecheck` | `npm.cmd` not found | 127 | 173 |
| `npm.cmd run lint` | `npm.cmd` not found | 127 | 177 |
| `npm.cmd test` | `npm.cmd` not found | 127 | 184 |

This confirms that the command block is Windows-specific. Substituting
`python3` and `npm` is necessary on this Linux image, but command-name changes
alone are not sufficient because a clean clone also lacks dependencies:

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `python3 factory/workbench_standard/generate_station_kits.py --check` | `jsonschema` missing | 1 | 246 |
| `python3 -m unittest discover -s factory/workbench_standard/tests -p "test_*.py" -v` | three import errors because `jsonschema` was missing | 1 | 300 |
| `python3 factory/enginectl.py doctor` | `jsonschema` missing | 1 | 281 |
| `npm run typecheck` | `tsc` not found | 127 | 601 |
| `npm run lint` | `eslint` not found | 127 | 324 |
| `npm test` | catalogue and contract checks passed, then `vinext` was not found | 127 | 950 |

### Explicit setup and adapted Linux run

The container did not include `pip` or `venv`. The first three setup commands
below are container prerequisites; the two `pip install` commands match the
locked dependency and REUSE versions documented in the repository root README.
The isolated environment was placed outside the clone.

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `python3 -m pip --version` | `pip` module not present | 1 | 196 |
| `apt-get update` | package metadata retrieved | 0 | 3,053 |
| `apt-get install -y python3-venv` | isolated-environment support installed | 0 | 3,122 |
| `python3 -m venv /tmp/ct001-venv` | isolated environment created | 0 | 4,837 |
| `/tmp/ct001-venv/bin/python -m pip install -r factory/requirements.lock` | locked Python dependencies installed | 0 | 7,489 |
| `/tmp/ct001-venv/bin/python -m pip install reuse==6.2.0` | documented REUSE version installed | 0 | 5,880 |

With `/tmp/ct001-venv/bin` first on `PATH`, the following commands were run:

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `reuse --version` | `reuse, version 6.2.0` | 0 | 546 |
| `reuse lint` | 2,063 of 2,063 files carried copyright and licence information; REUSE 3.3 compliant | 0 | 1,036 |
| `python factory/workbench_standard/generate_station_kits.py --check` | 100 station kits verified | 0 | 1,716 |
| `python -m unittest discover -s factory/workbench_standard/tests -p "test_*.py" -v` | 39 tests passed | 0 | 2,109 |
| `python factory/enginectl.py doctor` | `ENGINE READY`; no hosted-provider dependency | 0 | 1,332 |
| `python -m unittest discover -s factory/engine/tests -t factory -p "test_*.py" -v` | 20 tests passed, no skips | 0 | 13,466 |
| `npm ci` | 506 packages installed; npm reported four moderate-severity audit findings and five pending install-script approvals | 0 | 38,926 |
| `npm run typecheck` | passed | 0 | 9,490 |
| `npm run lint` | passed | 0 | 6,412 |
| `npm test` | build passed, but the test launcher timed out waiting for `http://localhost:4344` | 1 | 98,100 |

The failed Linux Hangar run reached the launcher's own 90-second timeout; it
was not left running. A bounded diagnostic showed that Node resolved
`localhost` to IPv6 before IPv4 in this container:

| Exact command | Result | Exit | Duration (ms) |
| --- | --- | ---: | ---: |
| `node -e "require('node:dns').lookup('localhost',{all:true},(error,addresses)=>{if(error)throw error;console.log(JSON.stringify(addresses))})"` | `::1` first, then `127.0.0.1` | 0 | 252 |
| `NODE_OPTIONS=--dns-result-order=ipv4first npm test` | build passed; 15 tests passed | 0 | 48,048 |
| `git status --short` | no tracked or untracked changes | 0 | 404 |

The IPv4-first rerun is evidence of a compatibility workaround, not a silent
replacement of the failed as-written result. The clean clone remained
unchanged, and no generated station-kit file was hand-edited.

## Findings

1. The repository checks are reproducible in clean Windows and Linux
   environments once their declared dependencies are installed.
2. `CONTRIBUTOR_QUICKSTART.md` is not currently sufficient by itself for a
   clean clone: it omits the locked Python/REUSE installation and `npm ci`.
3. Its common-check block is PowerShell-specific. Linux needs a documented
   `python3`/virtual-environment path and `npm` rather than `npm.cmd`.
4. The Hangar test launcher has a Linux/container `localhost` resolution
   divergence. The unmodified command timed out; forcing IPv4-first resolution
   made all 15 tests pass.
5. Both final `git status --short` checks were empty. No generated kit was
   edited, and no scientific work was performed.

These runs establish cross-environment construction compatibility evidence.
They do not establish independent-human reproduction or scientific standing.

The same construction change adds the missing locked setup and platform command
names to `CONTRIBUTOR_QUICKSTART.md`. It also changes the Hangar test launcher
to bind and probe `127.0.0.1` explicitly. Those remediations do not rewrite the
clean-clone observations above; the original failures remain part of this
record.
