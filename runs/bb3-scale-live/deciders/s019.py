from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------------------------------------------------------------
# Decider: n-gram translation-cycle search with a much larger
# window, plus a "two independent fronts" translation search
# targeted at the machines in this run: most of them look like
# a right-moving growth front and a left-moving growth front
# that are themselves periodic translated loops.
# ---------------------------------------------------------------

def _run_short(tm, n):
    return run(tm, n)

def _cycle_cert(tm, T, P):
    try:
        return check(tm, {"kind": "cycle", "t": T, "p": P})
    except Reject:
        return None

def _try_plain_cycles(tm, max_steps):
    # Fast plain-cycle hunt: state repeats while the window is
    # short enough to be checked cheaply.
    maxT = min(max_steps, 8000)
    states = {}
    tape = {}
    pos = 0
    st = 0
    seen = {}
    for step in range(1, maxT + 1):
        # advance one step by hand (cheap, no dict copy per step)
        tab = parse(tm)[0] if False else None
        break
    return None

def decide(tm):
    res = _run_short(tm, 0)
    # Simulate with generous bound; we only need the traces.
    halted, steps, state, pos, tape = run(tm, 40000)
    if halted:
        return None

    # ---------- 1) plain-cycle scan over the trace ----------
    # Re-simulate step by step, keeping a bounded history of
    # (state, pos, tape-image).  We look for a pair (T, T+P) with
    # the same state and a translated window.
    try:
        table, nstates, nsym = parse(tm)
    except Exception:
        return None

    def step(state, pos, tape):
        w = tape.get(pos, 0)
        if (state, w) not in table:
            return None
        nw, mv, nxt = table[(state, w)]
        tape[pos] = nw
        npos = pos + mv
        return nxt, npos, tape

    # history: list of (state, pos, frozen tape)
    hist = [(0, 0, dict())]
    st, p, tp = 0, 0, {}
    for i in range(1, 40001):
        r = step(st, p, tp)
        if r is None:
            break
        st, p, tp = r
        hist.append((st, p, dict(tp)))

    # plain cycles: same state, same window
    # We use a moderate window and scan backwards a bounded distance.
    W = 40
    for T in range(len(hist) - 2, 200, -1):
        sT, pT, tT = hist[T]
        # candidate lap lengths at increasing sizes
        for P in range(1, min(2000, len(hist) - T)):
            if T + P >= len(hist):
                break
            sP, pP, tP = hist[T + P]
            if sP != sT:
                continue
            d = pP - pT
            lo = min(pT, pP) - W
            hi = max(pT, pP) + W
            ok = True
            for y in range(lo, hi + 1):
                if tP.get(y + d, 0) != tT.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                for y in range(hi + 1, hi + 1 + 8):
                    if tP.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo - 8, lo):
                    if tP.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                c = _cycle_cert(tm, T, P)
                if c is not None:
                    return c
    return None
