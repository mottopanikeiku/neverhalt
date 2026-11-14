import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

HALT = object()

def decide(tm):
    try:
        table, n, m = parse(tm)
    except Exception:
        return None
    try:
        return _search(table, n)
    except Exception:
        return None

def _search(table, n):
    # Build the halting successors of each (q,s): normally one, but a
    # halting transition is an absent entry; a context that steps into an
    # absent transition is rejected by the kernel, so we never accept one.
    trans = {}
    for q in range(n):
        for s in range(2):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                trans[(q, s)] = (w, mv, q2)
            else:
                trans[(q, s)] = None

    # Automaton state ids are 0..S-1; state 0 must be the all-blank half-tape:
    # left[0][0] == 0 and, for a state whose tape is blank, looping on 0 is
    # required for a meaningful automaton (the hint explicitly says so).
    S = 4
    results = []
    for tl in _all_tables(S):
        if tl[0][0] != 0:
            continue
        for tr in _all_tables(S):
            if tr[0][0] != 0:
                continue
            cert = _close(table, trans, n, tl, tr)
            if cert is not None:
                return cert
    return None

def _all_tables(S):
    # Every function state -> {0,1} -> state or None.  Yield all tables.
    funcs = []
    for target in range(S + 1):
        funcs.append(target)
    out = []
    size = (S + 1) ** (2 * S)
    for code in range(size):
        c = code
        t = []
        for _ in range(S):
            row = []
            for _ in range(2):
                row.append(c % (S + 1)); c //= (S + 1)
            t.append(row)
        out.append(t)
    return out

def _close(table, trans, n, tl, tr):
    # Context = (l, q, s, r).  A context is accepted by the kernel only if it
    # never steps into an absent transition; the closure must contain [0,0,0,0].
    # We close forward: start from [0,0,0,0] and derive successors that must
    # also be contexts.  If some derived context is halting, this pair fails.
    # If the closure is empty of halting contexts, the certificate is the set.
    seen = set()
    stack = [(0, 0, 0, 0)]
    contexts = set()
    while stack:
        l, q, s, r = stack.pop()
        if (l, q, s, r) in seen:
            continue
        seen.add((l, q, s, r))
        contexts.add((l, q, s, r))
        trn = trans.get((q, s))
        if trn is None:
            return None
        w, mv, q2 = trn
        if mv == 1:
            l2 = tl[l][w]
            if l2 is None:
                return None
            # pop from right: (r2, s2) with tr[r2][s2] == r
            for r2 in range(len(tr)):
                row = tr[r2]
                for s2 in range(2):
                    if row[s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            stack.append(nxt)
        else:
            r2 = tr[r][w]
            if r2 is None:
                return None
            for l2 in range(len(tl)):
                row = tl[l2]
                for s2 in range(2):
                    if row[s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            stack.append(nxt)
    # Emit the certificate.
    left = [[None, None] for _ in range(len(tl))]
    for i, row in enumerate(tl):
        for x in range(2):
            left[i][x] = row[x]
    right = [[None, None] for _ in range(len(tr))]
    for i, row in enumerate(tr):
        for x in range(2):
            right[i][x] = row[x]
    ctx = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left, "right": right, "contexts": ctx}
