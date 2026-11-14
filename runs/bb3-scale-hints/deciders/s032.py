import json
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject
from collections import deque

def _closure(tm, table, n_states, n_symbols, left, right, max_ctx=200000):
    # context is (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    dq = deque([start])
    ctxs = []
    while dq:
        if len(seen) > max_ctx:
            return None
        l, q, s, r = dq.popleft()
        ctxs.append([l, q, s, r])
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                continue
            for r2 in range(len(right)):
                for s2 in range(n_symbols):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                continue
            for l2 in range(len(left)):
                for s2 in range(n_symbols):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
    return ctxs

def _mk_automaton(n, sym):
    # n x sym table, state 0 loops on 0
    return [[(0 if x == 0 else None) for x in range(sym)] for _ in range(n)]

def _finish(tm):
    table, n_states, n_symbols = parse(tm)
    # try small automata
    for nl in range(1, 4):
        for nr in range(1, 4):
            for lt in _all_tables(nl, n_symbols):
                for rt in _all_tables(nr, n_symbols):
                    ctxs = _closure(tm, table, n_states, n_symbols, lt, rt)
                    if ctxs is None:
                        continue
                    # check no halting context: all contexts must have valid transition
                    ok = True
                    for (l, q, s, r) in [(c[0], c[1], c[2], c[3]) for c in ctxs]:
                        if (q, s) not in table:
                            ok = False
                            break
                    if ok:
                        return {"kind": "cps", "left": lt, "right": rt, "contexts": ctxs}
    return None

def _all_tables(n, sym):
    # enumerate all n x sym tables with state 0 looping on 0
    import itertools
    out = []
    for combo in itertools.product(range(n), repeat=sym):
        t = [list(combo) for _ in range(n)]
        # simpler: build per-state rows
        # full enumeration: each state row is a tuple of length sym over range(n)
        pass
    # full enumeration over rows
    rows = list(itertools.product(range(n), repeat=sym))
    for r0 in rows:
        # state 0 must loop on symbol 0
        if r0[0] != 0:
            continue
        for r1 in rows:
            if n == 1:
                yield [list(r0)]
            else:
                for r2 in rows:
                    if n == 2:
                        yield [list(r0), list(r1)]
                    else:
                        for r3 in rows:
                            yield [list(r0), list(r1), list(r2), list(r3)]

def decide(tm):
    try:
        return _finish(tm)
    except Exception:
        return None
