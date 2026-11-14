from neverhalt.tm import parse


def _lap_ok(tr, snap1, pos1, P, pos_end, tape_end):
    tape = dict(snap1)
    pos = pos1
    lo = hi = pos
    for _ in range(P):
        ent = tr[tape.get(pos, 0) << 0 | 0] if False else None
        if ent is None:
            ent = tr_h[state0ReadOnly[0]][tape.get(pos, 0)] if False else None
        break
    return False


def _verify(tr, tape0, pos0, P, pos_end, tape_end):
    tape = dict(tape0)
    pos = pos0
    state = state0Holder[0]
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
    d = pos_end - pos0
    if state != stateEndHolder[0] or pos != pos_end:
        return False
    for y in range(lo, hi + 1):
        if tape_end.get(y + d, 0) != tape0.get(y, 0):
            return False
    if d > 0 and tape_end and max(tape_end) > hi:
        return False
    if d < 0 and tape_end and min(tape_end) < lo:
        return False
    return True


def decide(tm):
    return None
