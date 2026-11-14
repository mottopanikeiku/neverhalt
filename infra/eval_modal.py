"""Deploy with: cd /tmp/neverhalt && modal deploy infra/eval_modal.py.

Only decider execution leaves the client. Returned protocol lines are untrusted;
neverhalt.remote checks all certificates with the local trusted kernel.
CPU-only, no secrets or network, at most 100 containers, no warm idle pool.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import modal

app = modal.App("neverhalt-eval")
image = modal.Image.debian_slim(python_version="3.11").add_local_python_source("neverhalt")


@app.function(
    image=image,
    cpu=2.0,
    memory=4096,
    max_containers=100,
    min_containers=0,
    scaledown_window=2,
    timeout=86400,
    block_network=True,
    secrets=[],
)
def evaluate_chunk(decider_source: str, machines: list[str], limit: float) -> tuple[list[str], str]:
    """Return raw sandbox stdout lines and the same missing-output diagnostic as Runner.

    sandbox.py installs per-machine alarms and a hard 2 GiB address-space limit.
    The outer wall timeout also covers import-time hangs and disabled alarms.
    Killing the process group prevents decider children surviving a finished chunk.
    """
    import neverhalt.sandbox

    sandbox = Path(neverhalt.sandbox.__file__)
    with tempfile.TemporaryDirectory(prefix="neverhalt-decider-") as directory:
        decider = Path(directory) / "decider.py"
        decider.write_text(decider_source)
        proc = subprocess.Popen(
            [sys.executable, "-I", str(sandbox), str(decider), str(limit)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(
                "\n".join(machines) + "\n", timeout=len(machines) * limit + 5
            )
            died = f"sandbox exited with code {proc.returncode}: {stderr[-300:]}"
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, _ = proc.communicate()
            died = "sandbox killed: chunk time budget exceeded (an uncatchable loop?)"
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return stdout.splitlines(), died
