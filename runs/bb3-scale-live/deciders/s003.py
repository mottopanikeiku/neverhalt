from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

# Decider: n-gram CPS with a wider window (up to 4 cells each side), plus a
# bounded search for translated cycles with larger laps.
def decide(tm):
    # --- pass 1: translated cycle search, longer laps ---
    try:
        res = _cycle_search(tm)
        if res is not None:
            return res
    except Exception:
        pass
    # --- pass 2: n-gram CPS, n up to 4 ---
    try:
        cert = _cps_ngram(tm, 4)
        if cert is not None:
            check(tm, cert)
            return cert
    except Exception:
        pass
    # --- pass 3: try smaller n in case kernel limits are hit ---
    for n in (3, 2):
        try:
            cert = _cps_ngram(tm, n)
            if cert is not None:
                check(tm, cert)
                return cert
        except Exception:
            continue
    return None


def _steps_state(table, n_states, state, pos, tape, n):
    for _ in range(n):
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, ns = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = ns
    return state, pos, tape


def _cycle_search(tm):
    from neverhalt.tm import run
    table, n_states, _ = parse(tm)
    # simulate a bounded prefix
    halted, steps, state, pos, tape = run(tm, 20000)
    if halted:
        return None
    # we need full history for window tracking; re-simulate storing snapshots
    state = 0
    pos = 0
    tape = {}
    snaps = []
    for i in range(3000):
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, ns = table[(state, tape.get(pos, 0))]
        tape[pos] = w
        pos += mv
        state = ns
        if i % 1 == 0 and i >= 1000:
            snaps.append((i, state, pos, dict(tape)))
    # look for repeated (state, pos) modulo translation
    seen = {}
    for (i, st, p, tp) in snaps:
        for (j, st2, p2, tp2) in snaps:
            if j <= i:
                continue
            d = p2 - p
            if st2 != st:
                continue
            # check tape translation on a window
            lo = min(tp.keys(), default=0) - 5
            hi = max(tp.keys(), default=0) + 5
            ok = True
            for y in range(lo, hi + 1):
                if tp2.get(y + d, 0) != tp.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            # check blank outside
            P = j - i
            if d > 0:
                for y in range(hi + 1, hi + 1 + d + 1):
                    if tp2.get(y, 0) != 0:
                        ok = False
                        break
            elif d < 0:
                for y in range(lo - 1 - abs(d), lo):
                    if tp2.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                cert = {"kind": "cycle", "t": i, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Exception:
                    continue
    return None


def _cps_ngram(tm, n):
    from neverhalt.tm import parse
    table, n_states, _ = parse(tm)
    # build ngram automata for left and right half-tapes
    # symbol alphabet {0,1}; states are tuples of last n cells
    def build():
        states = [()]
        idx = {(): 0}
        trans = []
        for s in states:
            row = []
            for x in (0, 1):
                ns = (s + (x,))[-n:] if n > 0 else ()
                if ns not in idx:
                    idx[ns] = len(states)
                    states.append(ns)
                row.append(idx[ns])
            trans.append(row)
        return idx, trans
    lidx, ltrans = build()
    ridx, rtrans = build()
    # left automaton reads cells left of head from far away towards the head
    # left[i][x] is state reached; but kernel wants left[i][x] as state index
    # We need left[0][0] == 0 and right[0][0] == 0; empty tuple is state 0.
    # For left: reading from far away towards head means the newest cell is nearest.
    # Our tuple stores oldest..newest, so appending is correct for reading order.
    # contexts: [l, q, s, r]
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(contexts):
            if q >= n_states:
                continue
            if (q, s) not in table:
                contexts.discard((l, q, s, r))
                changed = True
                continue
            w, mv, q2 = table[(q, s)]
            if mv == 1:
                l2 = ltrans[l][w]
                for r2 in range(len(ridx)):
                    for s2 in (0, 1):
                        if rtrans[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
            else:
                r2 = rtrans[r][w]
                for l2 in range(len(lidx)):
                    for s2 in (0, 1):
                        if ltrans[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
    # check closure
    for (l, q, s, r) in contexts:
        if (q, s) not in table:
            return None
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            l2 = ltrans[l][w]
            for r2 in range(len(ridx)):
                for s2 in (0, 1):
                    if rtrans[r2][s2] == r and (l2, q2, s2, r2) not in contexts:
                        return None
        else:
            r2 = rtrans[r][w]
            for l2 in range(len(lidx)):
                for s2 in (0, 1):
                    if ltrans[l2][s2] == l and (l2, q2, s2, r2) not in contexts:
                        return None
    cert = {
        "kind": "cps",
        "left": [[None if x is None else x for x in row] for row in ltrans],
        "right": [[None if x is None else x for x in row] for row in rtrans],
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    return cert
}