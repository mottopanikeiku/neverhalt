NAME = "cps_ngram"

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _build(n):
    """Deterministic n-gram automaton for one half-tape.

    States are tuples of the last (at most n) cells read from far away towards
    the head; the all-blank tuple is canonicalised to () and becomes state 0.
    """
    states = [()]
    index = {(): 0}
    for length in range(1, n + 1):
        for bits in range(1 << length):
            tup = tuple((bits >> (length - 1 - i)) & 1 for i in range(length))
            if not any(tup):
                continue
            if tup not in index:
                index[tup] = len(states)
                states.append(tup)
    fwd = {}
    for st in states:
        i = index[st]
        for c in (0, 1):
            nt = (st + (c,))[-n:]
            if not any(nt):
                nt = ()
            fwd[(i, c)] = index[nt]
    rev = {}
    for i in range(len(states)):
        for c in (0, 1):
            rev.setdefault(fwd[(i, c)], []).append((i, c))
    return states, fwd, rev


def _try(tm, tree, n):
    states, fwd, rev = _build(n)
    if len(states) > 4700:
        return None
    start = (0, 0, 0, 0)          # blank left, state A, symbol 0, blank right
    seen = {start}
    work = [start]
    while work:
        l, q, s, r = work.pop()
        tr = tree.get((q, s))
        if tr is None:            # halting transition inside the invariant
            return None
        w, mv, q2 = tr
        if mv == 1:               # head moves right
            l2 = fwd[(l, w)]
            for (r2, s2) in rev.get(r, ()):   # pop nearest right cell
                ctx = (l2, q2, s2, r2)
                if ctx not in seen:
                    seen.add(ctx)
                    work.append(ctx)
        else:                     # head moves left
            r2 = fwd[(r, w)]
            for (l2, s2) in rev.get(l, ()):   # pop nearest left cell
                ctx = (l2, q2, s2, r2)
                if ctx not in seen:
                    seen.add(ctx)
                    work.append(ctx)
    if len(seen) > 180000:
        return None
    m = len(states)
    table = [[fwd[(i, 0)], fwd[(i, 1)]] for i in range(m)]
    cert = {"kind": "cps", "left": table, "right": table,
            "contexts": [list(ctx) for ctx in seen]}
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert


def decide(tm):
    try:
        tree, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    for n in range(1, 12):
        try:
            cert = _try(tm, tree, n)
        except Exception:
            cert = None
        if cert is not None:
            return cert
    return None
