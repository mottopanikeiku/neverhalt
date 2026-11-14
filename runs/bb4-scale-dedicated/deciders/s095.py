import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject, check


def _build_tables(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def _closure(table, ns, left, right, contexts):
    cur = list(contexts)
    seen = set((l, q, s, r) for l, q, s, r in cur)
    out = []
    while cur:
        nxt = []
        for l, q, s, r in cur:
            if (l, q, s, r) in seen:
                continue
            seen.add((l, q, s, r))
            out.append((l, q, s, r))
            tr = table.get((q, s))
            if tr is None:
                return None
            w, move, q2 = tr
            if move == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                for r2 in range(len(right)):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            nxt.append((l2, q2, s2, r2))
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            nxt.append((l2, q2, s2, r2))
        cur = nxt
    return out


def _small_automata(k):
    tables = []
    total = (k + 1) ** k
    for code in range(total):
        t = []
        c = code
        for i in range(k):
            row = []
            for x in range(2):
                row.append(c % (k + 1))
                c //= (k + 1)
            t.append(row)
        if t[0][0] != 0:
            continue
        tables.append(t)
    return tables


def decide(tm):
    try:
        table, ns, nsym = _build_tables(tm)
    except Exception:
        return None
    if ns > 4:
        return None
    for k in (1, 2, 3):
        for left in _small_automata(k):
            for right in _small_automata(k):
                seed = [(0, 0, 0, 0)]
                ctx = _closure(table, ns, left, right, seed)
                if ctx is None:
                    continue
                cert = {
                    "kind": "cps",
                    "left": left,
                    "right": right,
                    "contexts": [list(c) for c in ctx],
                }
                try:
                    check(tm, cert)
                except Reject:
                    continue
                return cert
    return None
