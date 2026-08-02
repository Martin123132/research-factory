from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import psutil


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str
    elapsed_ns: int
    peak_rss_bytes: int
    timed_out: bool
    output_limit_exceeded: bool


def kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        root = psutil.Process(process.pid)
        descendants = root.children(recursive=True)
    except psutil.Error:
        descendants = []
        root = None
    for child in reversed(descendants):
        try:
            child.kill()
        except psutil.Error:
            pass
    if root is not None:
        try:
            root.kill()
        except psutil.Error:
            pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _rss_tree(process_id: int) -> int:
    try:
        root = psutil.Process(process_id)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0
    total = 0
    for process in processes:
        try:
            total += int(process.memory_info().rss)
        except psutil.Error:
            pass
    return total


def run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    output_limit_bytes: int,
    environment: Mapping[str, str] | None = None,
) -> ProcessOutcome:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    started = time.perf_counter_ns()
    process = subprocess.Popen(
        list(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, env=dict(environment) if environment is not None else None,
        creationflags=creationflags,
    )
    if process.stdout is None or process.stderr is None:
        kill_process_tree(process)
        raise RuntimeError("failed to create candidate output pipes")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limit_event = threading.Event()
    counter_lock = threading.Lock()
    captured = 0

    def drain(name: str, pipe: object) -> None:
        nonlocal captured
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                return
            with counter_lock:
                remaining = max(0, output_limit_bytes - captured)
                if remaining:
                    buffers[name].extend(chunk[:remaining])
                    captured += min(len(chunk), remaining)
                if len(chunk) > remaining:
                    limit_event.set()

    threads = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds
    peak_rss = 0
    timed_out = False
    while process.poll() is None:
        peak_rss = max(peak_rss, _rss_tree(process.pid))
        if limit_event.is_set():
            kill_process_tree(process)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            kill_process_tree(process)
            break
        time.sleep(0.005)
    elapsed = time.perf_counter_ns() - started
    try:
        returncode = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        kill_process_tree(process)
        returncode = process.returncode if process.returncode is not None else -9
    for thread in threads:
        thread.join(timeout=2)
    process.stdout.close()
    process.stderr.close()
    return ProcessOutcome(
        returncode=int(returncode), stdout=bytes(buffers["stdout"]).decode("utf-8", errors="replace"),
        stderr=bytes(buffers["stderr"]).decode("utf-8", errors="replace"), elapsed_ns=elapsed,
        peak_rss_bytes=peak_rss, timed_out=timed_out, output_limit_exceeded=limit_event.is_set(),
    )
