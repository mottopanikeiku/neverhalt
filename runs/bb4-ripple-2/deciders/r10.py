from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def decide(tm):
    table, ns, nsym = parse(tm)
    tr = [[None] * nsym for _ in range(ns)]
    for (st, sym), ent in table.items():
        tr[st][sym] = ent

    # try small canonical automata side by side, states pinned 0..n-1
    for n in (3, 4, 5, 6):
        left = _canon(n, nsym)
        for right in left:
            cert = _close_safe(tr, left, right, ns, nsym)
            if cert is None:
                continue
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None


def _canon(n, nsym):
    # deterministic canonical linear tables: state i -> target (i * c + d) mod n
    # state 0 loops on symbol 0; rest cycle through states in a stable order
    out = []
    for c in range(1, n):
        for d in range(n):
            row = []
            for i in range(n):
                tgt = (i * c + d) % n
                if i == 0 and c == 0:
                    tgt = 0
                row.append(tgt)
            tab = []
            for i in range(n):
                r = [row[i]] * nsym
                tab.append(r)
            out.append(tab)
        # all-zero loop table is state 0 only
    base = [[0] * nsym for _ in range(n)]
    out.append(base)
    return out


def _close_safe(tr, left, right, ns, nsym):
    na = len(left)
    nb = len(right)
    if not (1 <= na <= 5000 and 1 <= nb <= 5000):
        return None
    for t in left:
        if not isinstance(t, list):
            return None
        for v in t:
            if not (isinstance(v, int) and 0 <= v < na):
                return None
    for t in right:
        if not isinstance(t, list):
            return None
        for v in t:
            if not (isinstance(v, int) and 0 <= v < nb):
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
