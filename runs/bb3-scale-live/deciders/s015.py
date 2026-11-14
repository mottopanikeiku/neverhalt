from neverhalt.tm import *
from neverhalt.kernel import check, Reject

# ---------------- helpers ----------------

def _step(tm, st, pos, tape):
    # returns (halted, st, pos, tape)
    n_states, n_symbols = None, None
    # use the module's run in chunks instead; we inline a fast local sim
    return None

def _simulate(tm, st, pos, tape, steps):
    # local simulation of `steps` steps; tape is dict pos->1
    for _ in range(steps):
        # decode machine
        pass
    return None

# We need a real per-machine simulation.  Use run() to get snapshots via
# repeated chunked calls is not possible (run always starts blank), so we
# re-implement a tiny interpreter here for the decider.

def _mach(tm):
    # parse once per call
    return parse(tm)

def _sim(tm, steps, snapshot_at=None):
    """Simulate blank start for `steps`, return (halted, st, pos, tape, snaps)."""
    table, n_states, n_symbols = parse(tm)
    st, pos = 0, 0
    tape = {}
    snaps = {}
    tgt = snapshot_at or []
    ti = 0
    for t in range(steps):
        if tgt and ti < len(tgt) and t == tgt[ti]:
            snaps[t] = (st, pos, dict(tape))
            ti += 1
        s = 0 if pos not in tape else 1
        key = (st, s)
        tr = table.get(key)
        if tr is None:
            return True, st, pos, tape, snaps
        w, mv, ns = tr
        if w:
            tape[pos] = 1
        else:
            tape.pop(pos, None)
        pos += mv
        st = ns
    return False, st, pos, tape, snaps

# ---------------- decider idea ----------------
# The samples show a very common pattern: a "sawtooth" / bouncing head that
# walks right, then left, returning to the same cell, while the tape grows
# by one cell per pass.  These are classic non-halting machines whose
# behaviour is an unbounded leftward drift with periodic structure.
#
# Strategy: run for a bounded number of steps and look for a *translated
# cycle* certificate: find T, P with the same state at T and T+P, and the
# tape shifted by d = pos(T+P) - pos(T) equals the tape in the window.
# We use a simple O(N^2) search over candidate (T,P) pairs from a simulation
# of, say, 4000 steps, checking the kernel's cycle condition directly.
# If a pair satisfies it, we hand the certificate to check() and return it
# if accepted.

def _try_cycle(tm, limit=4000):
    table, n_states, n_symbols = parse(tm)
    st, pos = 0, 0
    tape = {}
    states = []
    poss = []
    tapes = []
    for t in range(limit):
        states.append(st); poss.append(pos); tapes.append(dict(tape))
        s = 0 if pos not in tape else 1
        tr = table.get((st, s))
        if tr is None:
            return None
        w, mv, ns = tr
        if w: tape[pos] = 1
        else: tape.pop(pos, None)
        pos += mv
        st = ns

    # candidate T from the second half; candidate P such that T+P < limit
    n = limit
    for T in range(n // 2, n - 1):
        stT = states[T]; posT = poss[T]
        for P in range(1, n - T):
            if states[T + P] != stT:
                continue
            d = poss[T + P] - posT
            # window of head positions during lap
            lo = min(poss[T:T + P + 1])
            hi = max(poss[T:T + P + 1])
            # check tape equality (content of positions that must match)
            ok = True
            for y in range(lo, hi + 1):
                if tape.get(y, 0) != tapes[T].get(y - d, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                # cells right of hi must be blank at T+P
                for y in range(hi + 1, poss[T + P] + 1):
                    if tapes[T + P].get(y, 0) != 0:
                        ok = False
                        break
                if not ok:
                    continue
            elif d < 0:
                for y in range(poss[T + P] - 1, lo - 1, -1):
                    if tapes[T + P].get(y, 0) != 0:
                        ok = False
                        break
                if not ok:
                    continue
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                k = check(tm, cert)
                if k:
                    return cert
            except Reject:
                pass
    return None

def decide(tm: str):
    try:
        return _try_cycle(tm, limit=4000)
    except Exception:
        return None
