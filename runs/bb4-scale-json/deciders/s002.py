import sys
sys.setrecursionlimit(1000000)

from neverhalt.tm import parse, run


def _simulate(tm, max_steps):
    table, n_states, n_symbols = parse(tm)
    return _step(table, n_states, n_symbols, max_steps)


def _step(table, n_states, n_symbols, max_steps):
    state = 0
    pos = 0
    tape = {}
    steps = 0
    while steps < max_steps:
        key = (state, tape.get(pos, 0))
        if key not in table:
            return (True, steps, state, pos, tape)
        w, mv, nxt = table[key]
        tape[pos] = w
        pos += mv
        state = nxt
        steps += 1
    return (False, steps, state, pos, tape)


def _read_window(tape, lo, hi):
    return tuple(tape.get(x, 0) for x in range(lo, hi + 1))


def _write_window(tape, lo, hi, w):
    for i, x in enumerate(range(lo, hi + 1)):
        tape[x] = w[i]


def _build_cycle_cert(tm, T, P):
    table, n_states, n_symbols = parse(tm)
    state = 0
    pos = 0
    tape = {}
    steps = 0
    while steps < T:
        key = (state, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, nxt = table[key]
        tape[pos] = w
        pos += mv
        state = nxt
        steps += 1
    state_T = state
    pos_T = pos
    tape_T = dict(tape)
    lo = hi = pos
    for _ in range(P):
        key = (state, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, nxt = table[key]
        tape[pos] = w
        pos += mv
        state = nxt
        if pos < lo:
            lo = pos
        if pos > hi:
            hi = pos
    d = pos - pos_T
    if state != state_T:
        return None
    for y in range(lo, hi + 1):
        src = y
        dst = y + d
        a = tape_T.get(src, 0)
        b = tape.get(dst, 0)
        if a != b:
            return None
    if d > 0:
        for y in range(hi + 1, hi + 1 + 20):
            if tape.get(y, 0) != 0:
                return None
    if d < 0:
        for y in range(lo - 20, lo):
            if tape.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": T, "p": P}


def _try_windows(tm, min_T, max_T, max_P, budget):
    if max_T - min_T > budget:
        max_T = min_T + budget
    for T in range(min_T, max_T + 1):
        table, n_states, n_symbols = parse(tm)
        state = 0
        pos = 0
        tape = {}
        saved = []
        steps = 0
        while steps < T:
            key = (state, tape.get(pos, 0))
            if key not in table:
                return None
            w, mv, nxt = table[key]
            tape[pos] = w
            pos += mv
            state = nxt
            steps += 1
            saved.append((state, pos, dict(tape)))
        if T > 0:
            state_T = saved[-1][0]
            pos_T = saved[-1][1]
            tape_T = saved[-1][2]
        else:
            state_T = 0
            pos_T = 0
            tape_T = {}
        for P in range(1, max_P + 1):
            st = state
            ps = pos
            tp = tape
            lo = hi = ps
            for _ in range(P):
                key = (st, tp.get(ps, 0))
                if key not in table:
                    break
                w, mv, nxt = table[key]
                tp[ps] = w
                ps += mv
                st = nxt
                if ps < lo:
                    lo = ps
                if ps > hi:
                    hi = ps
            if st != state_T:
                continue
            d = ps - pos_T
            ok = True
            for y in range(lo, hi + 1):
                if tape_T.get(y, 0) != tp.get(y + d, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                for y in range(hi + 1, hi + 1 + 30):
                    if tp.get(y, 0) != 0:
                        ok = False
                        break
            if d < 0:
                for y in range(lo - 30, lo):
                    if tp.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    return None


def _try_short(tm, max_T, max_P):
    for T in range(0, max_T + 1):
        table, n_states, n_symbols = parse(tm)
        state = 0
        pos = 0
        tape = {}
        saved = []
        steps = 0
        while steps < T:
            key = (state, tape.get(pos, 0))
            if key not in table:
                return None
            w, mv, nxt = table[key]
            tape[pos] = w
            pos += mv
            state = nxt
            steps += 1
            saved.append((state, pos, dict(tape)))
        if T > 0:
            state_T = saved[-1][0]
            pos_T = saved[-1][1]
            tape_T = saved[-1][2]
        else:
            state_T = 0
            pos_T = 0
            tape_T = {}
        for P in range(1, max_P + 1):
            st = state
            ps = pos
            tp = tape
            lo = hi = ps
            for _ in range(P):
                key = (st, tp.get(ps, 0))
                if key not in table:
                    break
                w, mv, nxt = table[key]
                tp[ps] = w
                ps += mv
                st = nxt
                if ps < lo:
                    lo = ps
                if ps > hi:
                    hi = ps
            if st != state_T:
                continue
            d = ps - pos_T
            ok = True
            for y in range(lo, hi + 1):
                if tape_T.get(y, 0) != tp.get(y + d, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                for y in range(hi + 1, hi + 1 + 30):
                    if tp.get(y, 0) != 0:
                        ok = False
                        break
            if d < 0:
                for y in range(lo - 30, lo):
                    if tp.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                return {"kind": "cycle", "t": T, "p": P}
    return None


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Fast path: look for short plain cycles and translated cycles.
    cert = _try_short(tm, 60, 60)
    if cert is not None:
        return cert

    cert = _try_windows(tm, 60, 120, 120, 6000)
    if cert is not None:
        return cert

    cert = _try_windows(tm, 120, 200, 200, 6000)
    if cert is not None:
        return cert

    return None