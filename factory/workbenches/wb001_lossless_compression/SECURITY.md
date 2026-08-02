# WB-001 security boundary

## Protected assets

- sealed holdout files and manifest;
- hidden baseline results and detailed candidate measurements;
- evaluator Ed25519 private key;
- one-shot token ledger; and
- host filesystem, credentials, network and Docker socket.

None of these assets is mounted into a candidate container. The only candidate
mounts are a content-addressed source snapshot, one corpus root and a temporary
work directory.

## Enforced prototype controls

- Docker `network=none`;
- read-only container root;
- numeric non-root user 65532;
- all Linux capabilities dropped;
- `no-new-privileges` and built-in seccomp;
- private cgroup namespace and no IPC shared memory;
- one CPU, 512 MiB RAM/swap and 64 PID limits;
- bounded file descriptors, process count, logs and operation time;
- candidate/corpus read-only mounts and a narrow writable work mount;
- source hashes rechecked after immutable staging;
- regular-file, link-count, size, determinism and exact-output checks; and
- forced removal of the complete named container after every outcome.

The qualification probe verifies blocked network resolution, blocked root
writes, zero effective capabilities, `NoNewPrivs=1`, seccomp filtering, absence
of the Docker socket/host canary and complete cleanup. A log-bomb fixture must
be rejected at the byte cap.

## Honest limitation

Docker Desktop uses a shared WSL2 Linux kernel. This is stronger than running a
candidate directly as the Windows user, but it is not the final trust boundary
for arbitrary public hostile code. Production should schedule each locked
container inside a fresh VM or isolated worker host with no user data and no
long-lived credentials. Promotion-grade timing also needs pinned hardware and
randomized paired baseline/candidate rounds; container startup timing in this
prototype is correctness-only.

The prototype Ed25519 private key is protected only by the ignored private
directory and host file permissions. A production evaluator should keep that
key in an OS-backed secret service or hardware-backed signer and expose only a
restricted signing operation to the worker.
