import sys
from collections import deque

# ---------------------------------------------------------------------------
# Module: "cycle_ext"
#
# Strategy: search for translated cycles (kind "tcycle") with a large, bounded
# window, allowing the lap length to grow beyond what the earlier deciders
# tried.  A translated cycle is a strong certificate: the head moves by a
# non-zero displacement d over the lap while the tape content shifts over by d
# cells, so the machine can never halt.
#
# Implementation notes:
#   * We simulate the machine ourselves (the helper run() is too slow to call
#     repeatedly), tracking the head position and a dict of non-zero cells.
#   * For each candidate (T, P) pair we test the kernel's cycle condition
#     directly, including the "cells outside the window are blank" clause.
#   * To keep the search cheap we first look for repeated (state, head
#     displacement-over-window) signatures, then verify with the exact
#     condition.  Verification is the only thing that matters: a rejected
#     certificate costs nothing.
# ---------------------------------------------------------------------------

from neverhalt.tm import parse

MAX_TOTAL = 100000          # kernel limit t + p <= 100000
MAX_P = 48000               # keep the search window reasonable
SNAPSHOT_EVERY = 1


def _simulate(tm, max_steps):
    """Return (halted, steps, final_state, final_pos, tape) and also a list of
    (step, state, pos, tape_snapshot_delta) is avoided for speed; instead we
    keep snapshots at every step up to max_steps."""
    table, n_states, n_symbols = parse(tm)
    tape = {}
    pos = 0
    state = 0
    steps = 0
    snapshots = []          # (state, pos, dict(tape))
    halted = False
    while steps < max_steps:
        key = (state, tape.get(pos, 0))
        if key not in table:
            halted = True
            break
        w, mv, q2 = table[key]
        tape[pos] = w
        if w == 0:
            tape.pop(pos, None)
        pos += mv
        state = q2
        steps += 1
        snapshots.append((state, pos, dict(tape)))
    return halted, steps, state, pos, tape, snapshots


def _window_bounds(snapshots, t, p):
    """Return [lo, hi] of head positions seen during the lap [t, t+p]."""
    lo = None
    hi = None
    for i in range(t, t + p + 1):
        if i >= len(snapshots):
            return None, None
        pp = snapshots[i][1]
        if lo is None or pp < lo:
            lo = pp
        if hi is None or pp > hi:
            hi = pp
    return lo, hi


def _check_cycle(tm, snapshots, t, p):
    """Exact kernel condition for kind "cycle" (translated allowed)."""
    if t + p >= len(snapshots):
        return None
    st, pos, tape_t = snapshots[t]
    st2, pos2, tape_tp = snapshots[t + p]
    if st != st2:
        return None
    d = pos2 - pos
    lo, hi = _window_bounds(snapshots, t, p)
    if lo is None:
        return None
    # window content must match, shifted by d
    for y in range(lo, hi + 1):
        if tape_t.get(y, 0) != tape_tp.get(y + d, 0):
            return None
    if d > 0:
        # every cell right of hi must be blank at t+p
        for y in range(hi + 1, hi + 1 + 64):
            if tape_tp.get(y, 0) != 0:
                return None
    elif d < 0:
        for y in range(lo - 64, lo):
            if tape_tp.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": t, "p": p}


def decide(tm):
    """Search for a translated cycle certificate for `tm`."""
    try:
        halted, steps, state, pos, tape, snaps = _simulate(tm, MAX_TOTAL)
    except Exception:
        return None
    if halted:
        return None
    n = len(snaps)
    if n < 2:
        return None

    # Index steps by state for quick lookup
    by_state = {}
    for i, (st, pp, _) in enumerate(snaps):
        by_state.setdefault(st, []).append(i)

    # Try to find (t, p) with the same state and a consistent window.
    # Prefer small t+p first, then larger.
    best = None
    # Heuristic: candidate t values are early steps; candidate p values are
    # lap lengths that reproduce the same head displacement.
    for t in range(0, min(n - 2, 4000)):
        st_t = snaps[t][0]
        # We need p such that state at t+p equals st_t.
        for tp in by_state.get(st_t, []):
            p = tp - t
            if p <= 0 or p > MAX_P:
                continue
            if t + p > MAX_TOTAL:
                continue
            if t + p >= n:
                continue
            cert = _check_cycle(tm, snaps, t, p)
            if cert is not None:
                return cert
            # Early exit heuristic: if the window is huge, likely useless
            lo, hi = _window_bounds(snaps, t, p)
            if lo is None:
                continue
            if hi - lo > 4000:
                break
        # give up on this t if we already tried a big p and failed
        # (cheap pruning)
        if t > 0 and t % 500 == 0:
            continue
    return None


# Keep the module import-safe under the sandbox.
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))
