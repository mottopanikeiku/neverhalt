import sys
from collections import deque

# ------------------------------------------------------------------
# Decider: "tcycle_hunt"
#
# Idea: the surviving holdouts are machines that keep expanding a blob
# forever.  A translated cycle certificate only needs a *repeating lap*
# plus an all-blank tail on the far side.  Instead of trusting a fixed
# window we grow the lap until the head has walked back over its whole
# trail, then look for a lap whose repeat leaves the rest of the tape
# blank.  To make the lap cheap we let the search stop as soon as the
# *whole visited span* is blank outside [lo,hi] and the displacement
# d is nonzero.
# ------------------------------------------------------------------

from neverhalt.tm import parse, run
from neverhalt.kernel import Reject


def _machine_state_at(tm, step):
    # parse once, then re-run; we only need one machine per call anyway
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    # We simulate ourselves so we can inspect the tape at arbitrary times.
    # State A = 0, blank = 0.
    tape = {}
    pos = 0
    state = 0
    t = 0

    # history[step] = (state, pos, dict snapshot of non-zero cells)
    hist = {}
    max_steps = 100000

    while t <= max_steps:
        # current cell
        cell = tape.get(pos, 0)
        tr = table.get((state, cell))
        if tr is None:
            return None  # halted: not a holdout for us
        w, mv, nxt = tr
        if w:
            tape[pos] = w
        pos += mv
        state = nxt
        t += 1
        hist[t] = (state, pos, dict(tape))

    return None


def _try_cycle(tm, T, P):
    from neverhalt.kernel import check
    cert = {"kind": "cycle", "t": T, "p": P}
    try:
        check(tm, cert)
        return cert
    except Exception:
        return None


# Search strategy: try every (T,P) with T+P <= 100000 on a coarse grid
# first (P chosen from divisors of observed periods), then refine.
def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    tape = {}
    pos = 0
    state = 0
    t = 0
    snap = {}
    max_steps = 120000

    while t < max_steps:
        cell = tape.get(pos, 0)
        tr = table.get((state, cell))
        if tr is None:
            return None
        w, mv, nxt = tr
        if w:
            tape[pos] = w
        pos += mv
        state = nxt
        t += 1
        # cheap periodicity probe: reuse a dict of (state,pos) -> first time
        key = (state, pos)
        if key in snap:
            T0 = snap[key]
            P0 = t - T0
            # candidate lap: from T0 to t, displacement over lap
            # try small multiples of P0 as well
            for mult in range(1, 40):
                P = P0 * mult
                if T0 + P > max_steps:
                    break
                cert = _try_cycle(tm, T0, P)
                if cert is not None:
                    return cert
        else:
            snap[key] = t

    return None