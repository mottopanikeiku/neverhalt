from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


NAME = "scan state flr"


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    for i in range(4):
        left, right, cert = _scan(table, n_symbols, i)
        if cert is not None:
            return cert
    return None


def _scan(table, n_symbols, depth):
    pairs = _tables(n_symbols, depth + 1)
    for i in range(len(pairs)):
        for j in range(i, len(pairs)):
            lt = pairs[i][0]
            rt = pairs[j][0]
            cert = _closure(table, lt, rt)
            if cert is not None:
                return None, None, cert
    return None, None, None


def _tables(n_symbols, k):
    states = []
    states.append([[0, 0]])
    for size in range(1, 3):
        cur = list(states[-1])
        nxt = []
        for st in cur:
            for a in range(2):
                for b in range(2):
                    cos = st + [a, b]
                    if len(cos) <= k:
                        nxt.append(cos)
        states.append(nxt)
    return [(autom, None) for autom in states]


def _closure(table, lt, rt):
    lt = _declare(lt, 2)
    rt = _declare(rt, 2)
    S = {(0, 0, 0, 0)}
    stack = list(S)
    while stack:
        l, q, s, r = stack.pop()
        tr = table.get((q, s))
        if tr is None:
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = lt(l, w) if 0 <= w < 2 else None
            if l2 is None:
                return None
            rn = rt(r, w)
            if rn is None:
                return None
            for s2 in (0, 1):
                c = (l2, q2, s2, rn)
                if c not in S:
                    S.add(c); stack.append(c)
                    if len(S) > 12000:
                        return None
        else:
            r2 = rt(r, w) if 0 <= w < 2 else None
            if r2 is None:
                return None
            ln = lt(l, w)
            if ln is None:
                return None
            for s2 in (0, 1):
                c = (ln, q2, s2, r2)
                if c not in S:
                    S.add(c); stack.append(c)
                    if len(S) > 12000:
                        return None
    cert = {"kind": "cps",
            "left": [[lt(a, x) for x in (0, 1)] for a in range(len(lt))],
            "right": [[rt(a, x) for x in (0, 1)] for a in range(len(rt))],
            "contexts": [[a, b, c, d] for a, b, c, d in S]}
    try:
        check(tm, cert)
    except Reject:
        return None
    except Exception:
        return None
    return cert


def _declare(raw, n_symbols):
    states = len(raw)
    return lambda q, x: raw[q][x]
