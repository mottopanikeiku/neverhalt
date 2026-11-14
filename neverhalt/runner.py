"""Trusted side of decider execution: sandbox the untrusted code, kernel-check what comes back."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import kernel

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path(__file__).with_name("sandbox.py")
BWRAP = shutil.which("bwrap")


def sandbox_cmd(decider: Path, limit: float) -> list[str]:
    """No network, no home directory, read-only filesystem. Without bubblewrap: rlimits and `python -I` only."""
    decider = decider.resolve()  # bwrap bind mounts need absolute paths
    py = [sys.executable, "-I", str(SANDBOX), str(decider), str(limit)]
    if not BWRAP:
        return py
    return [BWRAP, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/home", "--tmpfs", "/tmp",
            "--ro-bind", str(ROOT), str(ROOT), "--ro-bind", str(decider.parent), str(decider.parent),
            "--unshare-all", "--die-with-parent", "--new-session", *py]


def run_chunk(decider: str, machines: list[str], limit: float) -> list[tuple]:
    """-> one (status, payload) per machine; status in proved | none | rejected | error | fatal."""
    try:
        proc = subprocess.run(sandbox_cmd(Path(decider), limit), input="\n".join(machines) + "\n",
                              capture_output=True, text=True, timeout=len(machines) * limit + 5)
        stdout, died = proc.stdout, f"sandbox exited with code {proc.returncode}: {proc.stderr[-300:]}"
    except subprocess.TimeoutExpired as e:
        raw = e.stdout or ""
        stdout = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
        died = "sandbox killed: chunk time budget exceeded (an uncatchable loop?)"
    results: list[tuple | None] = [None] * len(machines)
    for line in stdout.splitlines():
        try:
            msg = json.loads(line)
            if "fatal" in msg:
                return [("fatal", str(msg["fatal"]))] * len(machines)
            i = msg["i"]
            if type(i) is not int or not 0 <= i < len(machines):
                continue
            if "err" in msg:
                results[i] = ("error", str(msg["err"]))
            elif msg["cert"] is None:
                results[i] = ("none", None)
            else:
                try:
                    results[i] = ("proved", {"kind": kernel.check(machines[i], msg["cert"]), "cert": msg["cert"]})
                except kernel.Reject as e:
                    results[i] = ("rejected", str(e))
        except Exception:
            continue  # garbage on the protocol channel proves nothing
    return [r or ("error", died) for r in results]


class Runner:
    def __init__(self, workers: int | None = None):
        self.workers = workers or max(2, min(12, (os.cpu_count() or 4) - 1))
        self.pool = ProcessPoolExecutor(self.workers)

    def run(self, decider: Path, machines: list[str], limit: float, deadline: float | None = None):
        """Yield (machines, results) chunk by chunk, as they finish. `limit`: seconds per machine.

        Chunks not yet started when `deadline` (a time.time() value) passes are cancelled and never yielded.
        """
        size = max(1, min(200, -(-len(machines) // (self.workers * 6))))
        chunks = [machines[i:i + size] for i in range(0, len(machines), size)]
        futures = {self.pool.submit(run_chunk, str(decider), chunk, limit): chunk for chunk in chunks}
        for future in as_completed(futures):
            if future.cancelled():
                continue
            yield futures[future], future.result()
            if deadline is not None and time.time() > deadline:
                for pending in futures:
                    pending.cancel()

    def close(self):
        self.pool.shutdown(cancel_futures=True)
