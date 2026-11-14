from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    table, ns, nsym = parse(tm)
    tr = [[None] * nsym for _ in range(ns)]
    for (st, sym), ent in table.items():
        tr[st][sym] = ent

    for na in (1, 2, 3):
        for nb in (1, 2, 3):
            for lin in _cands(na, nsym):
                for rout in _cands(nb, nsym):
                    if na == 1 and nb == 1:
                        cert = _close_tr(tr, lin, rout, ns, nsym)
                        if cert is not None:
                            try:
                                check(tm, cert)
                                return cert
                            except Reject:
                                pass
    return None


def _cands(n, nsym):
    if n == 1:
        return [[[0, 0]], [[0, 1]], [[1, 0]], [[1, 1]]]
    tail = [[0, 0]]
    grids = []
    for g in _cands(n - 1, nsym):
        for last in (0, 1):
            new = [row[:] for row in g]
            new.append([0] * nsym)          # new state: 0 on both
            new[-1][0] = last               # state 0 loops on 0
            new[-1][1] = last
            grids.append(new)
    grids.append([[0, 0]] + [[0] * nsym for _ in range(n - 1)])
    for i in range(1, len(grids)):
        for x in range(nsym):
            pass
    seen = set()
    uniq = []
    for g in grids:
        key = tuple(tuple(r) for r in g)
        if key not in seen:
            seen.add(key)
            uniq.append(g)
    return uniq[:40]


def _close_tr(tr, lin, rout, ns, nsym):
    na = len(lin)
    nb = len(rout)
    left = [row[:] for row in lin]
    right = [row[:] for row in rout]
    contexts = {(0, 0, 0, 0)}
    while True:
        new = set()
        for (l, q, s, r) in contexts:
            ent = tr[q][s]
            if ent is None:
                return None
            w, mv, q2 = ent
            if mv == +1:
                lr = None
                for i in range(na):
                    if left[i][w] is not None:
                        lr = left[i][w]
                        break
                if lr is None:
                    continue
                for i in range(nb):
                    for s2 in range(nsym):
                        if right[i][s2] == r:
                            ctx = (lr, q2, s2, i)
                            if ctx not in contexts:
                                new.add(ctx)
            else:
                rr = None
                for i in range(nb):
                    if right[i][w] is not None:
                        rr = right[i][w]
                        break
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
    if len(contexts) > 200000:
        return None
    cert = {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    for (l, q, s, r) in contexts:
        if tr[q][s] is None:
            return None
    return cert
