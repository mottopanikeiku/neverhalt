import sys
from neverhalt.tm import parse, run

sys.setrecursionlimit(100000)

# ---------------------------------------------------------------------------
# A decider built around *counter machines* plus a "window vote" fallback.
#
# Idea: most surviving holdouts look like a small "block" (a pair of states
# that writes a 2-cell pattern and shuttles across the tape) that keeps
# marching outward, with a "tail" state that sweeps back and forth and leaves
# a fixed residue.  Such machines are non-halting because they either (a)
# enter a translated cycle whose period grows linearly with the block size,
# or (b) leave behind a periodic residue that a small automaton can describe.
#
# The window vote: sample the tape at a fixed set of relative offsets around
# the head and count how often each offset pattern repeats with a fixed
# displacement.  If a candidate translated cycle is found, certify it via the
# kernel's "cycle" certificate (the only one we need to construct here).
# ---------------------------------------------------------------------------

from neverhalt.kernel import check, Reject


def _state_at(tape, pos, base):
    return tape.get(pos, 0)


def _try_cycle(tm, max_steps=120000):
    """Look for a translated cycle (d != 0) in the run.

    We simulate and record snapshots (state, pos, tape-window) every step.
    Then we look for pairs (T, T+P) with the same state, the same window
    contents shifted by d, and the outside cells blank.
    """
    halted, steps, state, pos, tape = run(tm, max_steps)
    if halted:
        return None

    # Re-run collecting a bounded amount of history.
    table, ns, nsym = parse(tm)
    # We'll simulate manually to keep snapshots (run() only gives final).
    from neverhalt.tm import Machine
    m = Machine(tm)
    hist = []
    m.reset()
    for _ in range(max_steps):
        hist.append((m.state, m.pos, dict(m.tape)))
        if not m.step():
            break
    if len(hist) < 4:
        return None

    # Candidate period: look at recent repeats of state+pos and check the
    # window invariant.
    def window(tape, pos, r=12):
        return tuple(tape.get(pos + i, 0) for i in range(-r, r + 1))

    # Try periods that are multiples of 2 (writes move in steps of 1 usually).
    n = len(hist)
    best = None
    for P in range(2, min(n, 4000), 2):
        T = n - 1 - P
        if T < 0:
            break
        s0, p0, t0 = hist[T]
        s1, p1, t1 = hist[n - 1]
        if s0 != s1:
            continue
        d = p1 - p0
        if d == 0:
            # plain cycle: check window equality
            r = 12
            ok = True
            for i in range(-r, r + 1):
                if t0.get(p0 + i, 0) != t1.get(p1 + i, 0):
                    ok = False
                    break
            if ok:
                # verify via kernel with a small lap
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
            continue
        # translated cycle: check window shift and boundary blankness
        r = 12
        lo, hi = p0 - r, p0 + r
        ok = True
        for y in range(lo, hi + 1):
            if t0.get(y, 0) != t1.get(y + d, 0):
                ok = False
                break
        if not ok:
            continue
        if d > 0:
            for y in range(hi + 1, hi + 1 + max(0, d) + 4):
                if t1.get(y, 0) != 0:
                    ok = False
                    break
        else:
            for y in range(lo - max(0, -d) - 4, lo):
                if t1.get(y, 0) != 0:
                    ok = False
                    break
        if not ok:
            continue
        cert = {"kind": "cycle", "t": T, "p": P}
        try:
            check(tm, cert)
            return cert
        except Reject:
            pass
    return None


def decide(tm):
    # Quick sanity: skip obviously halting machines (kernel would reject anyway).
    try:
        cert = _try_cycle(tm)
        if cert is not None:
            return cert
    except Exception:
        return None
    return None
