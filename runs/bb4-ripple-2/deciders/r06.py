from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    table, ns, nsym = parse(tm)
    tr = [[None] * nsym for _ in range(ns)]
    for (st, sym), ent in table.items():
        tr[st][sym] = ent

    SIGS = 16
    LIMIT = 20000

    tape = {}
    pos = 0
    state = 0
    seen = {}
    t = 0
    lap_budget = 20000

    while t < LIMIT:
        ent = tr[state][tape.get(pos, 0)]
        if ent is None:
            return None
        w, mv, nxt = ent
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = nxt
        t += 1
        if t % SIGS:
            continue
        sig = (state, frozenset((p - pos, v) for p, v in tape.items()))
        rec = seen.get(sig)
        if rec is None:
            seen[sig] = [(t, pos, dict(tape))]
            continue
        if len(rec) > 6:
            continue
        for (t1, pos1, snap1) in reversed(rec):
            P = t - t1
            if P < 2 or P > 3000 or lap_budget < P:
                break
            lap_budget -= P
            if _lap_like(tr, snap1, pos1, state, P, pos, state, tape):
                cert = {"kind": "cycle", "t": t1, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None


def _lap_like(tr, snap1, pos1, st1, P, pos2, st2, tape2):
    tape = dict(snap1)
    pos = pos1
    state = st1
    lo = hi = pos
    for _ in range(P):
        ent = tr[state][tape.get(pos, 0)]
        if ent is None:
            return False
        w, mv, nxt = ent
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = nxt
        if pos < lo:
            lo = pos
        if pos > hi:
            hi = pos
    if state != st2 or pos != pos2:
        return False
    d = pos2 - pos1
    for y in range(lo, hi + 1):
        if tape2.get(y + d, 0) != snap1.get(y, 0):
            return False
    if d > 0 and tape2 and max(tape2) > hi:
        return False
    if d < 0 and tape2 and min(tape2) < lo:
        return False
    return True
