"""Exhaustive enumeration of n-state machines in tree normal form (TNF).

Start from the machine whose only transition is A0 -> wRB and simulate. Whenever the head
reaches an undefined transition, that machine halts there (recorded), and every way of
defining the transition becomes a child. Only behaviour on the blank tape matters, so this
covers all machines up to symmetry:
  * first move is R (mirror image), first jump goes to B (A0 -> ..A never halts: it keeps
    reading blanks in state A), states are named in order of first use (relabelling);
  * the last undefined transition is never filled in: a machine without undefined
    transitions cannot halt.
A machine still running after max_steps is a HOLDOUT: it needs a non-halting certificate.
If every holdout gets one, the longest halting run is the Busy Beaver value S(n).
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path


def _fmt(table, n, k):
    return "_".join(
        "".join("---" if (tr := table[q * k + s]) is None else f"{tr[0]}{'R' if tr[1] > 0 else 'L'}{chr(65 + tr[2])}"
                for s in range(k))
        for q in range(n))


def _search(stack, n, k, max_steps, frontier=None):
    """Depth-first when frontier is None; otherwise breadth-first until the stack holds `frontier` nodes."""
    halting, best, holdouts = 0, (0, None), []
    while stack and (frontier is None or len(stack) < frontier):
        table, tape, pos, q, steps, used = stack.pop() if frontier is None else stack.pop(0)
        tape = bytearray(tape)
        while steps < max_steps:
            tr = table[q * k + tape[pos]]
            if tr is None:
                break
            tape[pos] = tr[0]
            pos += tr[1]
            q = tr[2]
            steps += 1
        else:
            holdouts.append(_fmt(table, n, k))
            continue
        halting += 1
        if steps + 1 > best[0]:
            best = (steps + 1, _fmt(table, n, k))
        if table.count(None) == 1:
            continue
        idx = q * k + tape[pos]
        frozen = bytes(tape)
        for w in range(k):
            for d in (1, -1):
                for q2 in range(min(used + 1, n)):
                    child = table.copy()
                    child[idx] = (w, d, q2)
                    stack.append((child, frozen, pos, q, steps, max(used, q2 + 1)))
    return halting, best, holdouts, stack


def _work(args):
    node, n, k, max_steps = args
    return _search([node], n, k, max_steps)[:3]


def enumerate_tnf(n: int, k: int = 2, max_steps: int = 300, cache_dir: Path | None = None) -> dict:
    """-> {"n","k","max_steps","enumerated","halting","champion": {"tm","steps"}, "holdouts": [tm, ...]}"""
    cache = cache_dir / f"tnf_{n}x{k}_{max_steps}.json" if cache_dir else None
    if cache and cache.exists():
        return json.loads(cache.read_text())
    blank = bytes(2 * max_steps + 3)
    roots = []
    for w in range(k):
        table = [None] * (n * k)
        table[0] = (w, 1, 1)
        roots.append((table, blank, max_steps + 1, 0, 0, 2))
    # the empty machine (A0 undefined) halts after one step
    halting, best, holdouts = 1, (1, _fmt([None] * (n * k), n, k)), []
    h, b, ho, frontier = _search(roots, n, k, max_steps, frontier=256)
    halting, best, holdouts = halting + h, max(best, b, key=lambda x: x[0]), holdouts + ho
    if frontier:
        with mp.Pool(min(os.cpu_count() or 4, 12)) as pool:
            for h, b, ho in pool.imap_unordered(_work, [(node, n, k, max_steps) for node in frontier], chunksize=4):
                halting += h
                best = max(best, b, key=lambda x: x[0])
                holdouts += ho
    holdouts.sort()
    out = {"n": n, "k": k, "max_steps": max_steps, "enumerated": halting + len(holdouts), "halting": halting,
           "champion": {"tm": best[1], "steps": best[0]}, "holdouts": holdouts}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
    return out
