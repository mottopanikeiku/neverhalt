import itertools
from neverhalt.tm import parse, run


def _cells(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def _trans(t, q, s):
    e = t.get((q, s))
    if e is None:
        return None
    w, mv, q2 = e
    return (w, mv, q2)


def _blank_ok(left, right):
    # state 0 must loop on symbol 0 on both sides
    if left[0][0] != 0 or right[0][0] != 0:
        return False
    return True


def _build_dfa(nstates, allowed):
    """Yield half-tape automata as (n, table) where table[i][x] is next state.
    Only transitions demanded by the search are enumerated, but we start by
    enumerating all tables of size <= nstates and filter by blank-loop."""
    out = []
    for n in range(1, nstates + 1):
        for tup in itertools.product(range(n), repeat=2 * n):
            tbl = [[tup[i * 2 + x] for x in range(2)] for i in range(n)]
            if not _blank_ok(tbl, tbl):
                continue
            out.append((n, tbl))
    return out


def _closure(table, ns, L, R, steps=200000):
    """Closed context set. Contexts are tuples (l, q, s, r). We iterate the
    rule until stable; a halting context terminates the whole search.
    Returns None if a halting context is reachable, else the set."""
    halting = set()
    for q in range(ns):
        for s in range(2):
            if _trans(table, q, s) is None:
                halting.add((q, s))
    if not halting:
        return set()
    ctx = {(0, 0, 0, 0)}
    frontier = list(ctx)
    seen = set(ctx)
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            e = _trans(table, q, s)
            if e is None:
                return None
            w, mv, q2 = e
            if mv > 0:
                # right move: left automaton reads w
                if w >= 2 or L[l][w] is None:
                    # this context cannot be closed: pruning point
                    pass
                l2 = L[l][w]
                if l2 is None:
                    # this context is already known to lead to a halt
                    return None
                for r2 in range(R.__len__()):
                    for s2 in range(2):
                        if R[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                nxt.append(c)
            else:
                r2 = R[r][w]
                if r2 is None:
                    return None
                for l2 in range(L.__len__()):
                    for s2 in range(2):
                        if L[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in seen:
                                seen.add(c)
                                nxt.append(c)
        frontier = nxt
        if len(seen) > 200000:
            return None
    return seen


def _emit(table, ns, L, R, ctx):
    left = [[L[i][x] for x in range(2)] for i in range(len(L))]
    right = [[R[i][x] for x in range(2)] for i in range(len(R))]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}


def decide(tm):
    table, ns, nsym = parse(tm)
    if nsym != 2:
        return None
    try:
        left_list = _build_dfa(3, None)
    except Exception:
        return None
    right_list = left_list
    # quick sanity: no halting transition at all means trivial cps with empty
    # context set? No: kernel requires [0,0,0,0] context and closure. We just
    # enumerate pairs.
    for (nl, L) in left_list:
        for (nr, R) in right_list:
            if not _blank_ok(L, R):
                continue
            ctx = _closure(table, ns, L, R)
            if ctx is None:
                continue
            if len(ctx) > 200000:
                continue
            if (0, 0, 0, 0) not in ctx:
                continue
            # verify no halting context is in the closure (kernel checks this)
            cert = _emit(table, ns, L, R, ctx)
            return cert
    return None
