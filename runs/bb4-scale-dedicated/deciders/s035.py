from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _build_tables(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def _closed_contexts(table, ns, left, right):
    # contexts: (l, q, s, r) with l, r ints, q in [0, ns), s in [0, 1]
    # left/right: list of lists; None allowed
    nL = len(left)
    nR = len(right)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        cur = frontier.pop()
        l, q, s, r = cur
        if q >= ns or s >= 2:
            continue
        tr = table.get((q, s))
        if tr is None:
            # halting context: this certificate cannot be used by kernel
            # but we can still return None; mark failure
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            # every r2, s2 with right[r2][s2] == r
            for r2 in range(nR):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(nL):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
    return ctx


def _to_cps(table, ns, left, right, ctx):
    nL = len(left)
    nR = len(right)
    L = []
    for i in range(nL):
        row = []
        for x in range(2):
            v = left[i][x]
            row.append(v)
        L.append(row)
    R = []
    for i in range(nR):
        row = []
        for x in range(2):
            v = right[i][x]
            row.append(v)
        R.append(row)
    contexts = []
    for (l, q, s, r) in sorted(ctx):
        contexts.append([l, q, s, r])
    return {"kind": "cps", "left": L, "right": R, "contexts": contexts}


def _blank_safe(left, right, ns):
    # 0 state must loop on 0
    if left[0][0] != 0 or right[0][0] != 0:
        return False
    return True


def _try_pair(table, ns, left, right):
    ctx = _closed_contexts(table, ns, left, right)
    if ctx is None:
        return None
    cert = _to_cps(table, ns, left, right, ctx)
    # verify locally if possible
    try:
        check(tm_str, cert)
        return cert
    except Exception:
        return None


def decide(tm: str):
    global tm_str
    tm_str = tm
    table, ns, nsym = _build_tables(tm)
    # enumerate small automata
    # 1 state
    for sizeL in range(1, 4):
        for sizeR in range(1, 4):
            # enumerate all tables of sizeL x 2 with state 0 looping on 0
            import itertools
            def enum_tables(size):
                rows = []
                for i in range(size):
                    for a in range(size):
                        for b in range(size):
                            if i == 0 and a != 0:
                                continue
                            if i == 0 and b != 0:
                                continue
                            yield [[a, b]]
            # generator for full tables
            def enum_tables_full(size):
                # each row: (dest on 0, dest on 1)
                choices = [(a, b) for a in range(size) for b in range(size)]
                if size == 0:
                    yield []
                    return
                for combo in itertools.product(choices, repeat=size):
                    if combo[0][0] != 0:
                        continue
                    yield [list(x) for x in combo]
            for L in enum_tables_full(sizeL):
                for R in enum_tables_full(sizeR):
                    if not _blank_safe(L, R, ns):
                        continue
                    cert = _try_pair(table, ns, L, R)
                    if cert is not None:
                        return cert
    return None


tm_str = None
