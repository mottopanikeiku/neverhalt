from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _lap_ok(tr, snap1, pos1, st1, P, pos_end, st_end, tape_end):
    tape = dict(snap1)
    pos = pos1
    state = st1
    lo = hi = pos
    for _ in range(P):
        ent = tr[state][tape.get(pos, 0)]
        if ent is None:
            return False
        w, mv, ns = ent
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = ns
        if pos < lo:
            lo = pos
        if pos > hi:
            hi = pos
    if state != st_end or pos != pos_end:
        return False
    d = pos_end - pos1
    for y in range(lo, hi + 1):
        if tape_end.get(y + d, 0) != snap1.get(y, 0):
            return False
    if d > 0:
        if tape_end and max(tape_end) > hi:
            return False
    elif d < 0:
        if tape_end and min(tape_end) < lo:
            return False
    return True


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    tr = [[None] * n_symbols for _ in range(n_states)]
    for (st, sym), (w, mv, ns) in table.items():
        tr[st][sym] = (w, mv, ns)

    LIMIT, C = 30000, 24
    PMAX = 8000
    MAX_CHECKS = 60
    MAX_LAP = 15000

    tape = {}
    pos = 0
    state = 0
    t = 0
    sigs = {}
    checks = 0
    lap_budget = MAX_LAP

    while t < LIMIT:
        ent = tr[state][tape.get(pos, 0)]
        if ent is None:
            return None
        w, mv, ns = ent
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = ns
        t += 1
        if t % C:
            continue
        sig = (state, frozenset((p - pos, v) for p, v in tape.items()))
        prev = sigs.get(sig)
        if prev is None:
            sigs[sig] = [(t, pos, dict(tape))]
            continue
        if len(prev) >= 8:
            continue
        for (t1, pos1, snap1) in reversed(prev):
            P = t - t1
            if P < 2 or P > PMAX or lap_budget < P:
                break
            lap_budget -= P
            checks += 1
            if checks > MAX_CHECKS:
                return None
            if _lap_ok(tr, snap1, pos1, state, P, pos, state, tape):
                cert = {"kind": "cycle", "t": t1, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
