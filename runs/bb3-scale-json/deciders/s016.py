import sys
sys.setrecursionlimit(1000000)
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _states_of(tm):
    t, ns, nsym = parse(tm)
    return t, ns, nsym

def _run_trace(tm, steps):
    t, ns, nsym = parse(tm)
    # manual simulation producing (state,pos,tape) per step
    tape = {}
    st = 0
    p = 0
    trace = [(st, p, dict(tape))]
    for _ in range(steps):
        if (st, tape.get(p, 0)) not in t:
            return None
        w, mv, nxt = t[(st, tape.get(p, 0))]
        tape[p] = w
        p += mv
        st = nxt
        trace.append((st, p, dict(tape)))
    return trace

def _lap_shift_cycle(tm, max_steps):
    # Look for a translated cycle: simulate, then find T, P such that the lap
    # reproduces the window content shifted by d.
    t, ns, nsym = parse(tm)
    # Simulate up to max_steps collecting states/positions
    tape = {}
    st = 0
    p = 0
    hist = [(st, p, dict(tape))]
    for _ in range(max_steps):
        if (st, tape.get(p, 0)) not in t:
            return None
        w, mv, nxt = t[(st, tape.get(p, 0))]
        tape[p] = w
        p += mv
        st = nxt
        hist.append((st, p, dict(tape)))
    # try all T < T+P <= len(hist)-1
    n = len(hist)
    for T in range(0, n - 1):
        sT, pT, tapeT = hist[T]
        for P in range(1, n - T):
            sE, pE, tapeE = hist[T + P]
            if sE != sT:
                continue
            d = pE - pT
            # collect positions seen during lap
            lo = pT
            hi = pT
            for i in range(T, T + P + 1):
                lo = min(lo, hist[i][1])
                hi = max(hi, hist[i][1])
            ok = True
            for y in range(lo, hi + 1):
                if tapeE.get(y + d, 0) != tapeT.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                blank = True
                for y in range(hi + 1, hi + d + 1):
                    if tapeE.get(y, 0) != 0:
                        blank = False
                        break
                if not blank:
                    continue
            elif d < 0:
                blank = True
                for y in range(lo + d, lo):
                    if tapeE.get(y, 0) != 0:
                        blank = False
                        break
                if not blank:
                    continue
            return {"kind": "cycle", "t": T, "p": P}
    return None

def _try_rewrite_left(tm):
    # Detect a right-moving pattern that writes a blank over a cell and never reads it again
    # (left-to-right erasure): state sequence returns while head is strictly right of all
    # nonzero cells of the window.
    t, ns, nsym = parse(tm)
    tape = {}
    st = 0
    p = 0
    hist = [(st, p, tuple(sorted(tape.items())))]
    for _ in range(2000):
        if (st, tape.get(p, 0)) not in t:
            return None
        w, mv, nxt = t[(st, tape.get(p, 0))]
        tape[p] = w
        p += mv
        st = nxt
        hist.append((st, p, tuple(sorted(tape.items()))))
    # find T,P with same state, P>0, d = pE-pT > 0, and all nonempty cells at T+P lie
    # strictly left of pT and are unchanged, and cells in [pT, pE) at T+P are blank
    n = len(hist)
    for T in range(0, n - 1):
        sT, pT, tapeT = hist[T]
        for P in range(1, n - T):
            sE, pE, tapeE = hist[T + P]
            if sE != sT or pE - pT <= 0:
                continue
            d = pE - pT
            ok = True
            for y in range(pT, pE + 1):
                if tapeE.get(y, 0) != 0:
                    ok = False
                    break
            if not ok:
                continue
            # everything left of pT must be unchanged and outside [pT, pE)
            ok = True
            for y in range(pT - 200, pT):
                if tapeE.get(y, 0) != tapeT.get(y, 0):
                    ok = False
                    break
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    return None

def decide(tm: str):
    try:
        cert = _lap_shift_cycle(tm, 12000)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    except Exception:
        pass
    try:
        cert = _try_rewrite_left(tm)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    except Exception:
        pass
    return None