NAME = "counter_pair"

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _build_tables(k):
    """Enumerate every half-tape automaton of at most k states.

    table[i] = (next0, next1): the state after reading symbol x at the tail of
    the half-tape, mapped so that state 0 is blank-looping on 0.
    We fix table[0] = (0, next1) and enumerate the rest.
    """
    tables = []
    # table for state count k, states 0..k-1, table[0][0] = 0 by convention.
    # Enumerate the remaining entries freely with values in 0..k-1.
    n = 2 * (k - 1)
    for mask in range((k ** n) if n == 0 else (k ** n)):
        if n == 0:
            rows = [(0, 0)]
        else:
            rows = []
            flat = mask
            for i in range(k):
                if i == 0:
                    a = 0
                else:
                    a = flat % k
                    flat //= k
                if i == 0:
                    b = 0 if k == 1 else flat % k
                    flat //= k
                else:
                    b = flat % k
                    flat //= k
                rows.append((a, b))
        table = [list(r) for r in rows]
        tables.append(table)
    return tables


def _closed(tw, tree):
    st0 = (0, 0, 0, 0)
    seen = {st0}
    work = [st0]
    while work:
        l, q, s, r = work.pop()
        tr = tree.get((q, s))
        if tr is None:
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = tw[0][l][w]
            for (r2, s2) in tw[1]["rev"].get(r, ()):
                ctx = (l2, q2, s2, r2)
                if ctx not in seen:
                    seen.add(ctx)
                    work.append(ctx)
        else:
            r2 = tw[0][r][w]
            for (l2, s2) in tw[1]["rev"].get(l, ()):
                ctx = (l2, q2, s2, r2)
                if ctx not in seen:
                    seen.add(ctx)
                    work.append(ctx)
    return seen


def _try(tm, tree, tw):
    if len(tw[0]) > 4700 or len(tw[1]) > 4700:
        return None
    ltab = tw[0]
    rtab = tw[1]
    lrows = [[ltab[i][0], ltab[i][1]] for i in range(len(ltab))]
    rrows = [[rtab[i][0], rtab[i][1]] for i in range(len(rtab))]
    if len(rrows) > 2 or len(lrows) > 2:
        return None
    seen = _closed((lrows, {"rev": tw[2]}), tree)
    if seen is None:
        return None
    if len(seen) > 190000:
        return None
    contexts = [list(c) for c in seen]
    cert = {"kind": "cps", "left": lrows, "right": rrows, "contexts": contexts}
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
    for k in (1, 2, 3):
        tables = _build_tables(k)
        for lt in tables:
            # right side: same pattern of non-blank transitions, mirrored indexing.
            for rt in tables:
                ltab = [[lt[i][0], lt[i][1]] for i in range(len(lt))]
                rtab = [[rt[i][0], rt[i][1]] for i in range(len(rt))]
                # rev[i] = list of (j, x) with table[j][x] == i, but the
                # automaton reads cells from far to near; we anchor instead by
                # the pre-image of the head's own state, so build the proper
                # reverse relation from the transition (j, x) -> table[j][x].
                lrev = {}
                rrev = {}
                for j in range(len(ltab)):
                    for x in (0, 1):
                        lrev.setdefault(ltab[j][x], []).append((j, x))
                for j in range(len(rtab)):
                    for x in (0, 1):
                        rrev.setdefault(rtab[j][x], []).append((j, x))
                try:
                    cert = _try(tm, tree, (ltab, rtab, lrev | rrev))
                except Exception:
                    cert = None
                if cert is not None:
                    return cert
    return None
