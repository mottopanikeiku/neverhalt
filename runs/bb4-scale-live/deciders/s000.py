import json
import re
from collections import deque
from neverhalt.tm import parse, run

# Decider: fast translated-cycle detector with a longer lap budget.
# We simulate the machine for a bounded horizon, then look for a pair of
# states (t, t+p) with equal state and a shift d != 0 such that the tape
# contents inside the swept window reproduce exactly, with blank fill on
# the far side.  This catches machines that are drifting with a period.

def _try_lap(tm, T, P):
    from neverhalt.kernel import check, Reject
    cert = {"kind": "cycle", "t": T, "p": P}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Run a bounded search for translated cycles.
    max_steps = 6000
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    if halted:
        return None
    # We cannot see intermediate tapes from run(); re-simulate ourselves.
    # Reimplement a small simulator that records (state, pos, tape) snapshots.
    # The tape is two-way infinite; we track a dict.
    try:
        tape = {}
        state = 0  # A
        pos = 0
        snapshot = []  # list of (state, pos, tuple of (k, v) sorted)
        steps = 0
        halted = False
        while steps < max_steps:
            key = (state, tape.get(pos, 0))
            tr = table.get(key)
            if tr is None:
                halted = True
                break
            w, move, q2 = tr
            tape[pos] = w
            pos += move
            state = q2
            steps += 1
            snapshot.append((state, pos, tuple(sorted(tape.items()))))
    except Exception:
        return None
    if halted:
        return None
    # Look for laps.  Keep it cheap: check recent states against all earlier
    # snapshots with the same state.
    n = len(snapshot)
    # Index snapshots by state.
    by_state = {}
    for i, (st, p, t) in enumerate(snapshot):
        by_state.setdefault(st, []).append(i)
    for i in range(n):
        st, p, t = snapshot[i]
        for j in by_state.get(st, []):
            if j >= i:
                continue
            P = i - j
            if P == 0 or P > 4000:
                continue
            # Compute head displacement over the lap.
            d = p - snapshot[j][1]
            # Collect window of head positions over the lap.
            lo = min(snapshot[k][1] for k in range(j, i + 1))
            hi = max(snapshot[k][1] for k in range(j, i + 1))
            if d == 0:
                # plain cycle: window must be same content
                # (already equal because state and tape dict same? not necessarily)
                # Check tape equality on [lo, hi].
                ok = True
                for y in range(lo, hi + 1):
                    if snapshot[i][2] and (y in dict(snapshot[i][2])):
                        pass
                # do full compare
                tj = dict(snapshot[j][2])
                ti = dict(snapshot[i][2])
                for y in range(lo, hi + 1):
                    if tj.get(y, 0) != ti.get(y, 0):
                        ok = False
                        break
                if not ok:
                    continue
                cert = {"kind": "cycle", "t": j, "p": P}
                from neverhalt.kernel import check, Reject
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
            else:
                # translated: compare window content shifted by d
                tj = dict(snapshot[j][2])
                ti = dict(snapshot[i][2])
                ok = True
                for y in range(lo, hi + 1):
                    if tj.get(y, 0) != ti.get(y + d, 0):
                        ok = False
                        break
                if not ok:
                    continue
                # check blank fill on far side: if d>0, cells right of hi at i must be blank
                if d > 0:
                    # every y > hi must be blank at i
                    for y in range(hi + 1, hi + 50):
                        if ti.get(y, 0) != 0:
                            ok = False
                            break
                else:
                    for y in range(lo - 50, lo):
                        if ti.get(y, 0) != 0:
                            ok = False
                            break
                if not ok:
                    continue
                cert = {"kind": "cycle", "t": j, "p": P}
                from neverhalt.kernel import check, Reject
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None
} 