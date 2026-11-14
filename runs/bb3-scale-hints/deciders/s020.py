import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def build_left_cps(tm, left, right):
    t, ns, nsym = parse(tm)
    maxlen = 200000
    seen = set()
    out = []
    q = deque([(0, 0, 0, 0)])
    seen.add((0, 0, 0, 0))
    while q:
        l, qq, s, r = q.popleft()
        key = (l, qq, s, r)
        if len(seen) > maxlen:
            return None
        out.append([l, qq, s, r])
        tr = t.get((qq, s))
        if tr is None:
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(nsym):
                    if right[r2][s2] == r:
                        k = (l2, q2, s2, r2)
                        if k not in seen:
                            seen.add(k)
                            q.append(k)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(nsym):
                    if left[l2][s2] == l:
                        k = (l2, q2, s2, r2)
                        if k not in seen:
                            seen.add(k)
                            q.append(k)
    return left, right, out

def make_cps(tm, left, right):
    try:
        res = build_left_cps(tm, left, right)
    except Exception:
        return None
    if res is None:
        return None
    l, r, contexts = res
    return {"kind": "cps", "left": l, "right": r, "contexts": contexts}

def try_cps(tm, left, right):
    cert = make_cps(tm, left, right)
    if cert is None:
        return None
    try:
        check(tm, cert)
    except Reject:
        return None
    except Exception:
        return None
    return cert

def gen_automata(n_states, n_symbols):
    idx = list(range(n_symbols))
    tables = []
    if n_states == 1:
        tables.append([[0, 0]])
        return tables
    for combo in range((n_states + 1) ** n_symbols):
        table = []
        ok = True
        for i in range(n_states):
            row = []
            for j in range(n_symbols):
                row.append(combo // ((n_states + 1) ** (j * n_states + i)) % (n_states + 1))
            table.append(row)
        if table[0][0] != 0:
            continue
        tables.append(table)
    return tables

def decide(tm):
    t, ns, nsym = parse(tm)
    for n in (1, 2, 3):
        for right in gen_automata(n, nsym):
            for left in gen_automata(n, nsym):
                cert = try_cps(tm, left, right)
                if cert is not None:
                    return cert
    return None