import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check

# Decider: "zoom_cycle" - searches for translated cycles with a head-displacement
# window, using a fast hand-rolled simulator instead of the library one.
# We simulate T steps, then try lap lengths P from 1 upward, checking the
# translated-cycle certificate condition directly.  We also try several
# starting offsets T by continuing the simulation further, which catches
# cycles whose preperiod is longer than the first guess.

NAME = "zoom_cycle"


def _step(tape, st, pos, table, ns):
    s = tape.get(pos, 0)
    key = (st, s)
    if key not in table:
        return None
    w, mv, nxt = table[key]
    if nxt >= ns:
        return None
    tape[pos] = w
    pos += mv
    return nxt, pos


def decide(tm):
    try:
        table, ns, _ = parse(tm)
    except Exception:
        return None
    n_st = ns
    tape = {}
    st = 0
    pos = 0
    # advance the machine step by step, remembering snapshots
    snaps = []
    max_steps = 100000
    steps = 0
    while steps < max_steps:
        snaps.append((st, pos, dict(tape)))
        r = _step(tape, st, pos, table, n_st)
        if r is None:
            return None
        st, pos = r
        steps += 1
    # try to find a translated cycle: for each T among the snapshots,
    # for P from 1 to 2000, check the condition.
    # To keep it cheap, iterate T over a coarser grid first.
    for T in range(0, len(snaps), 7):
        stT, posT, tapeT = snaps[T]
        # extend the run beyond the snapshots if needed
        # (simulate additional steps from here)
        tape2 = dict(tapeT)
        st2 = stT
        pos2 = posT
        cur = (st2, pos2, dict(tape2))
        for P in range(1, 1500):
            r = _step(tape2, st2, pos2, table, n_st)
            if r is None:
                break
            st2, pos2 = r
            if P % 1 == 0:
                cur = (st2, pos2, dict(tape2))
                # check cycle condition at T+P
                if st2 == stT:
                    d = pos2 - posT
                    # determine window [lo,hi] of head positions during the lap
                    # recompute by re-simulating the lap
                    t2 = dict(tapeT)
                    s2 = stT
                    p2 = posT
                    lo = p2
                    hi = p2
                    ok = True
                    for _ in range(P):
                        s2, p2 = _step(t2, s2, p2, table, n_st) if False else (None, None)
                        break
                    # do it properly
                    t2 = dict(tapeT)
                    s2 = stT
                    p2 = posT
                    lo = p2
                    hi = p2
                    for _ in range(P):
                        r = _step(t2, s2, p2, table, n_st)
                        if r is None:
                            ok = False
                            break
                        s2, p2 = r
                        if p2 < lo:
                            lo = p2
                        if p2 > hi:
                            hi = p2
                    if not ok:
                        break
                    # now t2 is the tape at T+P
                    if d == 0:
                        # plain cycle: tape_T == tape_{T+P} on [lo,hi]
                        good = True
                        for y in range(lo, hi + 1):
                            if t2.get(y, 0) != tapeT.get(y, 0):
                                good = False
                                break
                        if good:
                            try:
                                cert = {"kind": "cycle", "t": T, "p": P}
                                check(tm, cert)
                                return cert
                            except Exception:
                                pass
                    else:
                        # translated cycle: tape_{T+P}[y+d] == tape_T[y] for y in [lo,hi]
                        good = True
                        if d > 0:
                            for y in range(lo, hi + 1):
                                if t2.get(y + d, 0) != tapeT.get(y, 0):
                                    good = False
                                    break
                            # cells right of hi must be blank at T+P
                            if good:
                                for y in range(hi + 1, hi + d + 1):
                                    if t2.get(y, 0) != 0:
                                        good = False
                                        break
                        else:
                            for y in range(lo, hi + 1):
                                if t2.get(y + d, 0) != tapeT.get(y, 0):
                                    good = False
                                    break
                            if good:
                                for y in range(lo + d, lo):
                                    if t2.get(y, 0) != 0:
                                        good = False
                                        break
                        if good:
                            try:
                                cert = {"kind": "cycle", "t": T, "p": P}
                                check(tm, cert)
                                return cert
                            except Exception:
                                pass
    return None
