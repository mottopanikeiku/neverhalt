"""Modal-backed Runner; all certificate verification remains on this machine.

Deploy infra/eval_modal.py first. RemoteRunner(workers=100) uses chunks of at
most 300 machines, reduced to distribute smaller evaluations across workers.
The deadline is a time.time() value: no new chunk is submitted after it passes;
already submitted calls finish and are yielded. close() cancels outstanding calls.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from . import kernel


def _parse_chunk(lines: list[str], died: str, machines: list[str]) -> list[tuple]:
    """Mirror runner.run_chunk's untrusted protocol handling, checking locally."""
    results: list[tuple | None] = [None] * len(machines)
    for line in lines:
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
            continue  # Garbage on the protocol channel proves nothing.
    return [r or ("error", died) for r in results]


class RemoteRunner:
    def __init__(self, workers: int | None = None):
        import modal

        self.workers = max(1, min(100, workers or 100))
        self.function = modal.Function.from_name("neverhalt-eval", "evaluate_chunk")
        self.pool = ThreadPoolExecutor(max_workers=self.workers)
        self._calls = set()
        self._lock = threading.Lock()

    def run(self, decider: Path, machines: list[str], limit: float, deadline: float | None = None):
        """Yield (chunk_machines, results) as remote chunks finish, as Runner does."""
        if not machines or (deadline is not None and time.time() >= deadline):
            return
        source = decider.read_text()
        size = max(1, min(300, -(-len(machines) // self.workers)))
        chunks = iter(machines[i:i + size] for i in range(0, len(machines), size))
        pending = {}

        def submit():
            if deadline is not None and time.time() >= deadline:
                return False
            chunk = next(chunks, None)
            if chunk is None:
                return False
            try:
                call = self.function.spawn(source, chunk, limit)
            except Exception as e:
                # Infrastructure errors never become proofs.
                raise RuntimeError(f"Modal could not start evaluation chunk: {e}") from e
            with self._lock:
                self._calls.add(call)
            pending[self.pool.submit(call.get)] = (call, chunk)
            return True

        try:
            for _ in range(self.workers):
                if not submit():
                    break
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    call, chunk = pending.pop(future)
                    with self._lock:
                        self._calls.discard(call)
                    try:
                        lines, died = future.result()
                        results = _parse_chunk(lines, died, chunk)
                    except Exception as e:
                        results = [("error", f"remote execution failed: {type(e).__name__}: {e}")] * len(chunk)
                    yield chunk, results
                    submit()
        finally:
            # Also clean up when a caller stops consuming the generator early.
            for future, (call, _) in pending.items():
                call.cancel()
                future.cancel()
                with self._lock:
                    self._calls.discard(call)

    def close(self):
        with self._lock:
            calls = list(self._calls)
            self._calls.clear()
        for call in calls:
            call.cancel()
        self.pool.shutdown(wait=True, cancel_futures=True)
