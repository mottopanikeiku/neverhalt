from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Try the classic "late" translation cycle: run a long prefix, then look for a
# window whose content repeats after a fixed shift.  This catches holdouts that
# only start sliding after the tape has grown large.

def _tcycle_search(tm, prefix, lap, window=40):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    try:
        halted, steps, state, pos, tape = run(tm, prefix + lap)
    except Exception:
        return None
    if not halted:
        pass
    else:
        # run shortened the trace; re-run to be safe
        pass
    # We need per-step snapshots.  Re-simulate manually to record them.
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    from neverhalt.tm import parse as _parse
    # manual simulation with snapshots
    state = 0
    pos = 0
    tape = {}
    snaps = []
    total = prefix + lap
    for i in range(total):
        s = tape.get(pos, 0)
        if (state, s) not in table:
            return None
        w, mv, ns = table[(state, s)]
        tape[pos] = w
        pos += mv
        state = ns
        snaps.append((state, pos, dict(tape)))
    if state is not None and (state, 0) not in table:
        # halting transition means it would halt on next read; not a cycle
        pass
    T = prefix
    P = lap
    if (state, 0) in table:
        pass
    # The tape at step T and T+P
    if T >= len(snaps) or T + P >= len(snaps):
        return None
    st, pT, tapeT = snaps[T]
    st2, p2, tape2 = snaps[T + P]
    if st != st2:
        return None
    # head displacement
    d = p2 - pT
    # window of head positions during the lap
    lo = min(s[1] for s in snaps[T:T + P])
    hi = max(s[1] for s in snaps[T:T + P])
    # check tape reproduction
    ok = True
    for y in range(lo, hi + 1):
        if tape2.get(y + d, 0) != tapeT.get(y, 0):
            ok = False
            break
    if not ok:
        return None
    # check blank outside requirement
    if d > 0:
        for y in range(hi + 1, hi + 1 + abs(d)):
            if tape2.get(y, 0) != 0:
                return None
    elif d < 0:
        for y in range(lo - 1, lo - 1 + abs(d)):
            if tape2.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": T, "p": P, "d": d}

def decide(tm: str) -> dict | None:
    # Try a range of prefix/lap sizes, longest lap first for budget reasons.
    for lap in (6000, 4000, 2000, 1000, 500, 200):
        for prefix in (40000, 20000, 10000, 5000, 2000, 1000):
            cert = _tcycle_search(tm, prefix, lap)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
                except Exception:
                    pass
    return None
