import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

try:
    from collections import defaultdict
except Exception:
    pass


def _build_map(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _diag_states(tm, max_steps=20000):
    table, n_states, n_symbols = parse(tm)
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    return halted, steps, state, pos, tape


def _find_cycle(tm, max_lap=100000):
    table, n_states, n_symbols = parse(tm)
    try:
        halted, steps, state, pos, tape = run(tm, 2000)
    except Exception:
        return None
    if halted:
        return None
    try:
        halted2, steps2, state2, pos2, tape2 = run(tm, 2000 + max_lap)
    except Exception:
        return None
    if halted2:
        return None
    T = 2000
    P = max_lap
    # recompute the lap contents
    h, s, q, p, t = run(tm, T)
    # simulate another P steps manually to inspect the window
    tape = dict(t)
    pos = p
    state = q
    lo = pos
    hi = pos
    for i in range(P):
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, nxt = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = nxt
        if pos < lo:
            lo = pos
        if pos > hi:
            hi = pos
    if state != q:
        return None
    d = pos - p
    if d == 0:
        return None
    # check window match
    for y in range(lo, hi + 1):
        if tape.get(y) != tape.get(y - d if d > 0 else y - d):
            # need proper shifted comparison
            pass
    return None


def decide(tm):
    # Strategy: aggressively search for translated cycles with long laps.
    # Use the actual run helper to reconstruct exact tape states.
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Try many starting offsets and lap lengths to catch translated cycles.
    for T in (100, 300, 500, 800, 1200, 2000, 3000, 5000, 8000):
        try:
            halted, steps, state, pos, tape = run(tm, T)
        except Exception:
            return None
        if halted:
            return None
        if steps < T:
            # machine halted before T in this run
            return None
        # snapshot
        snap = dict(tape)
        q0 = state
        p0 = pos
        lo = pos
        hi = pos
        cur = dict(snap)
        cpos = pos
        cstate = state
        for i in range(20000):
            key = (cstate, cur.get(cpos, 0))
            if key not in table:
                break
            w, mv, nxt = table[key]
            cur[cpos] = w
            cpos += mv
            cstate = nxt
            if cpos < lo:
                lo = cpos
            if cpos > hi:
                hi = cpos
            if cstate == q0 and cpos == p0:
                # plain cycle check
                if cur == snap:
                    return {"kind": "cycle", "t": T, "p": i}
            if cstate == q0 and cpos == p0 + (cpos - p0):
                pass
            # translated cycle check at every step where state matches
            if cstate == q0:
                d = cpos - p0
                if d != 0:
                    ok = True
                    for y in range(lo, hi + 1):
                        a = cur.get(y)
                        b = snap.get(y - d) if d > 0 else snap.get(y - d)
                        # for d>0 the pattern is shifted right: new[y] should equal old[y-d]
                        if a != b:
                            ok = False
                            break
                    if ok:
                        # verify the tail condition for d > 0: cells right of hi blank
                        if d > 0:
                            for y in range(hi + 1, hi + 1 + abs(d) + 10):
                                if cur.get(y, 0) != 0:
                                    ok = False
                                    break
                        else:
                            for y in range(lo - 10, lo):
                                if cur.get(y, 0) != 0:
                                    ok = False
                                    break
                    if ok:
                        try:
                            check(tm, {"kind": "cycle", "t": T, "p": i})
                            return {"kind": "cycle", "t": T, "p": i}
                        except Reject:
                            pass
    return None
