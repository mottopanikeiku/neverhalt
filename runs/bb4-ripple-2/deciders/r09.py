from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    table, ns, nsym = parse(tm)
    tr = [[None] * nsym for _ in range(ns)]
    for (st, sym), ent in table.items():
        tr[st][sym] = ent

    for na in (2, 3, 4):
        ltab = _grid(na, nsym)
        for rout in _grid(na, nsym):
            left = ltab
            right = rout
            cert = _close(tr, left, right, ns, nsym)
            if cert is None:
                continue
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None


def _grid(n, nsym):
    # table: state i, row entries all target states in range; canonical rotation
    g = [[i % n for _ in range(nsym)] for i in range(n)]
    return g


def _close(tr, left, right, ns, nsym):
    na = len(left)
    nb = len(right)
    if not (0 <= na <= 5000 and 0 <= nb <= 5000):
        return None
    for t in left:
        for v in t:
            if v is not None and not (0 <= v < na):
                return None
    for t in right:
        for v in t:
            if v is not None and not (0 <= v < nb):
                return None
    contexts = {(0, 0, 0, 0)}
    while True:
        new = set()
        for (l, q, s, r) in contexts:
            if not (0 <= l < na and 0 <= r < nb):
                return None
            ent = tr[q][s]
            if ent is None:
                return None
            w, mv, q2 = ent
            if mv == +1:
                if not (0 <= l < na):
                    return None
                lr = left[l][w]
                if lr is None:
                    continue
                for i in range(nb):
                    for s2 in range(nsym):
                        if right[i][s2] == r:
                            ctx = (lr, q2, s2, i)
                            if ctx not in contexts:
                                new.add(ctx)
            else:
                if not (0 <= r < nb):
                    return None
                rr = right[r][w]
                if rr is None:
                    continue
                for i in range(na):
                    for s2 in range(nsym):
                        if left[i][s2] == l:
                            ctx = (i, q2, s2, rr)
                            if ctx not in contexts:
                                new.add(ctx)
        if not new:
            break
        contexts |= new
        if len(contexts) > 120000:
            return None
    for (l, q, s, r) in contexts:
        if tr[q][s] is None:
            return None
    return {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
