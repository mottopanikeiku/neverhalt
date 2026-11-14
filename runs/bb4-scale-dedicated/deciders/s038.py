import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _table(tm):
    """Return (n_states, n_symbols, trans) where trans[(q,s)]=(w,move,q2) or None."""
    table, nq, ns = parse(tm)
    out = {}
    for (q, s), v in table.items():
        w, mv, q2 = v
        out[(q, s)] = (int(w), (1 if mv == "+1" else -1), int(q2))
    return nq, ns, out


def _build_left_table(tm):
    """Automaton reading cells left of the head, far away -> head.
    State 0 = all-blank half-tape. Rows indexed by automaton state, columns by symbol."""
    nq, ns, trans = _table(tm)

    def mk(nstates):
        t = [[None] * ns for _ in range(nstates)]
        t[0][0] = 0
        return t

    # candidate small automata; state 0 loops on 0
    cands = []
    for nst in (1, 2, 3):
        cands.append(mk(nst))
    return cands


def _build_right_table(tm):
    nq, ns, trans = _table(tm)

    def mk(nstates):
        t = [[None] * ns for _ in range(nstates)]
        t[0][0] = 0
        return t

    cands = []
    for nst in (1, 2, 3):
        cands.append(mk(nst))
    return cands


def _fill_left_candidate(tm, base):
    """base: left table with state 0 loop on 0. Return list of completed tables."""
    nq, ns, trans = _table(tm)
    out = []
    nst = len(base)
    # try all assignments for the remaining rows/cols by BFS over reachable cells
    # simple approach: enumerate deterministic assignments for states 1..nst-1
    import itertools

    free_states = list(range(1, nst))
    if not free_states:
        out.append([row[:] for row in base])
        return out
    # each free row has ns columns, each either 0..nst-1
    choices = list(itertools.product(range(nst), repeat=ns))
    for combo in choices:
        t = [row[:] for row in base]
        ok = True
        for i, st in enumerate(free_states):
            for x in range(ns):
                t[st][x] = combo[i * ns + x]
        out.append(t)
    return out


def _fill_right_candidate(tm, base):
    return _fill_left_candidate(tm, base)


def _closure(tm, left, right, left_trans, right_trans, max_ctx=200000):
    """Compute the smallest closed context set, or None if one is needed but not closed.
    Context = (l, q, s, r). Returns (contexts, halting) or None."""
    nq, ns, trans = _table(tm)
    ctx = set()
    start = (0, 0, 0, 0)
    ctx.add(start)
    frontier = [start]
    halting = False
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            v = trans.get((q, s))
            if v is None:
                halting = True
                return None
            w, mv, q2 = v
            if mv > 0:
                l2 = left[l][w]
                if l2 is None:
                    return None
                # pop nearest cell s2 off right: every (r2,s2) with right[r2][s2]==r
                for r2 in range(len(right)):
                    for s2 in range(ns):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in range(ns):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
        frontier = nxt
        if len(ctx) > max_ctx:
            return None
    return ctx, halting


def _emit(tm, left, right, ctx):
    L = [[None] * len(ctx) for _ in range(len(left))]
    R = [[None] * len(ctx) for _ in range(len(right))]
    # kernel wants left/right as transition tables indexed by automaton state
    # rows: automaton state, columns: symbol. We store as list of lists.
    cert = {
        "kind": "cps",
        "left": [list(row) for row in left],
        "right": [list(row) for row in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in sorted(ctx)],
    }
    return cert


def decide(tm):
    try:
        nq, ns, trans = _table(tm)
    except Exception:
        return None

    # quick sanity: try to find any certificate; first try the trivial
    # 1-state automata (both sides) with all transitions forced to 0
    left_cands = _build_left_table(tm)
    right_cands = _build_right_table(tm)

    for lb in left_cands:
        for rb in right_cands:
            try:
                lcs = _fill_left_candidate(tm, lb)
                rcs = _fill_right_candidate(tm, rb)
            except Exception:
                continue
            for left in lcs:
                for right in rcs:
                    res = _closure(tm, left, right, None, None)
                    if res is None:
                        continue
                    ctx, halting = res
                    if halting:
                        continue
                    cert = _emit(tm, left, right, ctx)
                    try:
                        from neverhalt.kernel import check
                        check(tm, cert)
                    except Exception:
                        continue
                    return cert
    return None


if __name__ == "__main__":
    import sys as _s
    for line in _s.stdin:
        line = line.strip()
        if not line:
            continue
        c = decide(line)
        print(line, "->", "None" if c is None else c["kind"])