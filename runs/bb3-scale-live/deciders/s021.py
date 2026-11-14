from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _table(tm):
    t, ns, nsym = parse(tm)
    return t, ns

def _step(t, q, s):
    return t.get((q, s))

def _detune(t, ns):
    # determine which transitions are halting (absent)
    return t

def _search_cycle(tm, max_sim=100000):
    t, ns = _table(tm)
    # simulate and look for a translated cycle with small period
    tape = {}
    q = 0
    p = 0
    seen = []
    # We do a BFS over (q, p, snapshot of a window) states is too big;
    # instead just simulate and detect periodic head/state/tape-window behaviour.
    # For a machine to be provably non-halting by cycle, often there is a
    # small window around the head that repeats.
    for step in range(max_sim):
        st = _step(t, q, tape.get(p, 0))
        if st is None:
            return None
        w, mv, q2 = st
        tape[p] = w
        p += mv
        q = q2
        # check for a translated cycle: compare current (q,p,tape) to past
        # states, but only if the window of tape around head is same.
        # Use a window of radius R around head.
        R = 12
        key = (q, p)
        win = tuple((tape.get(y, 0), y - p) for y in range(p - R, p + R + 1))
        # normalize relative to head
        win = tuple((tape.get(p + d, 0), d) for d in range(-R, R + 1))
        found = None
        for i, (qq, pp) in enumerate(seen):
            if qq == q:
                # candidate lap length
                lap = step - i
                if lap <= 0:
                    continue
                # check head displacement and tape shift
                # we need tape_{T+P}[y+d] == tape_T[y] for window [lo,hi]
                # and blank far side
                # compute d
                d = p - pp
                # window in absolute coords at time i
                lo_i = pp - R
                hi_i = pp + R
                # window at time step
                lo_s = p - R
                hi_s = p + R
                ok = True
                # overlap region: cells that are in both windows
                # tape_T[y] for y in [lo,hi] must equal tape_{T+P}[y+d]
                # We need tape_T[y] == tape_{T+P}[y+d] for y in [lo_i, hi_i]
                # But tape_T only known for cells we've seen; use dict get
                for y in range(lo_i, hi_i + 1):
                    if tape.get(y, 0) != tape.get(y + d, 0):
                        # but note tape has been updated; we need snapshots.
                        ok = False
                        break
                if not ok:
                    continue
                # far side blank check
                if d > 0:
                    # every cell right of hi_s (absolute at T+P) blank at T+P
                    for y in range(hi_s + 1, hi_s + d + R + 1):
                        if tape.get(y, 0) != 0:
                            ok = False
                            break
                elif d < 0:
                    for y in range(lo_s - 1, lo_s + d - R - 1, -1):
                        if tape.get(y, 0) != 0:
                            ok = False
                            break
                if ok:
                    found = (i, step, lap, d)
                    break
        if found:
            i, step, lap, d = found
            T = i
            P = lap
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
        seen.append((q, p))
        if len(seen) > 4000:
            break
    return None

def decide(tm: str):
    return _search_cycle(tm)
