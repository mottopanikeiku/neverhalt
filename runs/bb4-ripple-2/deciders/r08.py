from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    table, ns, nsym = parse(tm)
    tr = [[None] * nsym for _ in range(ns)]
    for (st, sym), ent in table.items():
        tr[st][sym] = ent

    LIMIT = 2500
    tape = {}
    pos = 0
    state = 0
    t = 0
    hi = 0
    lo = 0
    while t < LIMIT:
        ent = tr[state][tape.get(pos, 0)]
        if ent is None:
            return None
        w, mv, nxt = ent
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        state = nxt
        t += 1
        if tape:
            hi = max(hi, max(tape))
            lo = min(lo, min(tape))

    if hi - lo > 88 or hi > 70:
        return None

    budget = 90000
    for na in (1, 2):
        for nb in (1, 2):
            for ltab in _cands(na, nsym):
                for rtab in _cands(nb, nsym):
                    cert = _close(tr, ltab, rtab, ns, nsym)
                    if cert is None:
                        continue
                    if budget <= 0:
                        return None
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None


def _cands(n, nsym):
    if n == 1:
        return [[[0, 0]], [[0, 1]], [[1, 0]], [[1, 1]]]
    rows = [0] + [0] * (n - 1)
    outthis = [[0] * nsym]
    # build n-row tables: first row all-zero-loop; extra rows vary then loop on 0
    res = []
    for g in _cands(n - 1, nsym):
        for last in (0, 1):
            row = [0] * nsym
            row[0] = last
            row[1] = last
            res.append(g + [row])
    res.append([[0] * nsym for _ in range(n)])
    return res


def _close(tr, lin, rtab, ns, nsym):
    na = len(lin)
    nb = len(rtab)
    left = lin
    right = rtab
    contexts = {(0, 0, 0, 0)}
    while True:
        new = set()
        for (l, q, s, r) in contexts:
            ent = tr[q][s]
            if ent is None:
                return None
            w, mv, q2 = ent
            if mv == +1:
                if not (0 <= l < na):
                    return None
                row = left[l]
                tgt = row[w]
                if tgt is None or not (0 <= tgt < na):
                    continue
                for i in range(nb):
                    if not (0 <= r < nb):
                        break
                    if right[i][s2ok] is None:
                        continue
                    if right[i][s2ok] == r:
                        ctx = (tgt, q2, s2ok, i)
                        if ctx not in contexts:
                            new.add(ctx)
            else:
                if not (0 <= r < nb):
                    return None
                tgt = right[r][w]
                if tgt is None or not (0 <= tgt < nb):
                    continue
                for i in range(na):
                    if not (0 <= l < na):
                        break
                    if left[i][s2ok] is None:
                        continue
                    if left[i][s2ok] == l:
                        ctx = (i, q2, s2ok, tgt)
                        if ctx not in contexts:
                            new.add(ctx)
        if not new:
            break
        contexts |= new
    if len(contexts) > 100000:
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
