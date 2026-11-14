from neverhalt.tm import parse, run
from neverhalt.kernel import check

# Idea: hunt translated cycles (kind "tcycle") by simulating each machine and
# looking for a repeated (state, head position) pair whose displacement and
# window reproduce.  The 37 surviving holdouts look like glider-like patterns
# that keep drifting, so a translated cycle is the most likely certificate.
# Strategy: simulate up to a generous horizon, and whenever the same state is
# seen at two positions with the same displacement over a candidate lap, test
# the window condition and hand the certificate to check().

def find_tcycle(tm, horizon=4000):
    parsed, parsed2 = None, None
    try:
        from neverhalt.tm import parse as _p, run as _r
    except Exception:
        return None
    try:
        table, ns, nsm = _p(tm)
    except Exception:
        return None
    try:
        halted, steps, state, pos, tape = _r(tm, horizon)
    except Exception:
        return None
    if halted:
        return None
    # Re-simulate while recording (state, pos) at each step and the tape.
    try:
        table, ns, nsm = _p(tm)
        tape = {}
        st = 0
        p = 0
        seen = {}
        snap = []
        for step in range(horizon):
            if st not in table:
                break
            key = (st, p)
            if key in seen:
                T = seen[key]
                lap = step - T
                # candidate lap
                cert = {"kind": "cycle", "t": T, "p": lap}
                try:
                    from neverhalt.kernel import check as _chk
                    _chk(tm, cert)
                    return cert
                except Exception:
                    pass
            if key not in seen:
                seen[key] = step
                snap.append((step, dict(tape), st, p))
            # step
            if st not in table:
                break
            entry = table.get((st, tape.get(p, 0)))
            if entry is None:
                break
            w, mv, nxt = entry
            tape[p] = w
            p = p + mv
            st = nxt
        # if we stopped at a halt or an undefined transition, no cycle found here
        return None
    except Exception:
        return None

def decide(tm: str):
    try:
        c = find_tcycle(tm, horizon=4000)
        if c is not None:
            return c
    except Exception:
        pass
    return None
