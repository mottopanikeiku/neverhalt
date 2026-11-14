import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(10000)


def _transitions(tm):
    table, ns, nsym = parse(tm)
    out = {}
    for q in range(ns):
        for s in (0, 1):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                out[(q, s)] = (w, mv, q2)
    return out, ns


def _state_map(tm):
    table, ns, _ = parse(tm)
    return ns


def _closure_contexts(nstates, trans, left, right):
    """Compute the smallest closed context set or None if it contains a halting context.

    trans: dict (q,s)->(w,move,q2). left/right: n x 2 tables, None allowed.
    Returns (contexts, ok) where contexts is a list of (l,q,s,r).
    """
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if (q, s) not in trans:
                return None, False
            w, mv, q2 = trans[(q, s)]
            if mv == +1:
                if left[l][w] is None:
                    return None, False
                l2 = left[l][w]
                for (r2, s2) in range(len(right)):
                    pass
                # need pairs (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
            else:  # mv == -1
                if right[r][w] is None:
                    return None, False
                r2 = right[r][w]
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
        frontier = nxt
    return sorted(ctx), True


def _emit_cps(tm, left, right, contexts):
    lc = [[None, None] for _ in range(len(left))]
    rc = [[None, None] for _ in range(len(right))]
    for i in range(len(left)):
        for x in (0, 1):
            v = left[i][x]
            if v is not None:
                lc[i][x] = v
    for i in range(len(right)):
        for x in (0, 1):
            v = right[i][x]
            if v is not None:
                rc[i][x] = v
    ctxs = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": lc, "right": rc, "contexts": ctxs}


def _try_pair(tm, trans, ns, left, right):
    if len(left) > 5000 or len(right) > 5000:
        return None
    ctx, ok = _closure_contexts(ns, trans, left, right)
    if not ok:
        return None
    if len(ctx) > 200000:
        return None
    cert = _emit_cps(tm, left, right, ctx)
    try:
        check(tm, cert)
    except Reject:
        return None
    except Exception:
        return None
    return cert


def _all_tables(nstates, allowed):
    """Enumerate deterministic automata with nstates states, symbols 0/1.

    Yields list of rows; row i is [f(i,0), f(i,1)] with None allowed.
    State 0 must be the blank state: row 0 = [0, 0].
    """
    if nstates == 1:
        yield [[0, 0]]
        return
    rows = [[None, None] for _ in range(nstates)]
    rows[0] = [0, 0]
    # enumerate remaining rows in lexicographic order over 0..nstates-1, None
    import itertools
    choices = list(range(nstates)) + [None]
    idx = list(itertools.product(choices, repeat=2))
    for combo in idx:
        if combo == (0, 0):
            continue
        rows[1] = list(combo)
        for rem in itertools.product(choices, repeat=2 * (nstates - 2)):
            for i in range(2, nstates):
                rows[i] = [rem[2 * (i - 2)], rem[2 * (i - 2) + 1]]
            yield [list(r) for r in rows]


def decide(tm: str):
    trans, ns = _transitions(tm)
    # quick sanity: if machine halts within budget, nothing to prove
    try:
        halted, steps, state, pos, tape = run(tm, 200)
        if halted:
            return None
    except Exception:
        pass

    # Phase 1: cheap bounded enumeration 1..3 states per side
    for la in range(1, 4):
        for lb in range(1, 4):
            for left in _all_tables(la, None):
                for right in _all_tables(lb, None):
                    cert = _try_pair(tm, trans, ns, left, right)
                    if cert is not None:
                        return cert

    # Phase 2: grow one automaton in BFS-canonical order up to 10 states,
    # with the other side also enumerated small.
    for la in range(1, 11):
        count = 0
        for left in _all_tables(la, None):
            count += 1
            if count > 200000:
                break
            for lb in range(1, 4):
                for right in _all_tables(lb, None):
                    cert = _try_pair(tm, trans, ns, left, right)
                    if cert is not None:
                        return cert
        if count > 200000:
            break

    return None


if __name__ == "__main__":
    import json
    import sys
    tm = sys.argv[1]
    r = decide(tm)
    if r is None:
        print(json.dumps({"none": True}))
    else:
        print(json.dumps(r))
