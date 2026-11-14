import json
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Small decider: try every 1-, 2-, 3-state automaton pair, plus a growing
# set of "counter-like" automata built from a small grammar, and emit the
# first closed-context certificate that the kernel accepts.

def _build_pairs(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return

    # collect the finite set of states that actually appear
    states = sorted({q2 for (_, _, w, mv, q2) in []})
    # reparse properly
    states = []
    for q in range(ns):
        for x in range(nsym):
            v = table.get((q, x))
            if v is not None:
                states.append(v[2])
    states = sorted(set(states))
    qstates = [0] + states

    def gen_tables(k):
        # all deterministic tables on 2 symbols over k states, state 0 loops on 0
        for tup in _gen(k):
            yield tup

    def _gen(k):
        idx = 0
        while True:
            if idx >= (k * k) ** (2 * (k - 1)):
                return
            t = []
            v = idx
            for _ in range(2 * (k - 1)):
                t.append(v % k)
                v //= k
            yield t
            idx += 1

    def to_table(t, k):
        tbl = [[0, 0] for _ in range(k)]
        tbl[0][0] = 0
        j = 0
        for i in range(1, k):
            tbl[i][0] = t[j % k]; j += 1
            tbl[i][1] = t[j % k]; j += 1
        return tbl

    def closure(left, right, qstates):
        # initialize contexts: (l, q, s, r)
        ctxs = set()
        ctxs.add((0, 0, 0, 0))
        while True:
            add = False
            cur = list(ctxs)
            for (l, q, s, r) in cur:
                if q >= len(qstates) or s not in (0, 1):
                    continue
                v = table.get((q, s))
                if v is None:
                    return None
                w, mv, q2 = v
                if mv == 1:
                    l2 = left[l][w]
                    if l2 is None:
                        return None
                    for (r2, s2) in right_range(right, r):
                        c = (l2, q2, s2, r2)
                        if c not in ctxs:
                            ctxs.add(c); add = True
                else:
                    r2 = right[r][w]
                    if r2 is None:
                        return None
                    for (l2, s2) in left_range(left, l):
                        c = (l2, q2, s2, r2)
                        if c not in ctxs:
                            ctxs.add(c); add = True
            if not add:
                break
        return ctxs

    def right_range(right, r):
        out = []
        for s2 in (0, 1):
            r2 = right[r][s2]
            if r2 is not None:
                out.append((r2, s2))
        return out

    def left_range(left, l):
        out = []
        for s2 in (0, 1):
            l2 = left[l][s2]
            if l2 is not None:
                out.append((l2, s2))
        return out

    best = None
    maxk = 3
    for k in range(1, maxk + 1):
        for lt in gen_tables(k):
            left = to_table(lt, k)
            for rt in gen_tables(k):
                right = to_table(rt, k)
                ctxs = closure(left, right, qstates)
                if ctxs is None:
                    continue
                if len(ctxs) > 200000 or len(set(l for l, _, _, _ in ctxs)) > 5000:
                    continue
                cert = {
                    "kind": "cps",
                    "left": [[(x if x is not None else None) for x in row] for row in left],
                    "right": [[(x if x is not None else None) for x in row] for row in right],
                    "contexts": [list(c) for c in ctxs],
                }
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

def decide(tm: str):
    return _build_pairs(tm)