from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

HALT = object()


def _trans(tm, q, s):
    t, ns, _ = parse(tm)
    try:
        w, mv, q2 = t[(q, s)]
    except KeyError:
        return None
    return (w, mv, q2)


def _dfa_closure(tm, left_tab, right_tab, start_ctx, max_ctx=200000, max_states=5000):
    """Close context set starting from start_ctx.

    Returns list of contexts [l, q, s, r] or None if a halting context is forced.
    """
    t, ns, _ = parse(tm)
    n_states = ns
    ctxs = {}
    seen = set()
    frontier = [start_ctx]
    while frontier:
        ctx = frontier.pop()
        key = tuple(ctx)
        if key in seen:
            continue
        seen.add(key)
        ctxs[key] = ctx
        if len(ctxs) > max_ctx:
            return None
        l, q, s, r = ctx
        tr = _trans(tm, q, s)
        if tr is None:
            return None  # halting context
        w, mv, q2 = tr
        if mv == 1:
            l2 = left_tab[l][w] if l < len(left_tab) else None
            if l2 is None:
                return None
            # right pops: for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right_tab)):
                row = right_tab[r2]
                for s2 in range(2):
                    if row[s2] == r:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in seen:
                            frontier.append(nctx)
        else:
            r2 = right_tab[r][w] if r < len(right_tab) else None
            if r2 is None:
                return None
            for l2 in range(len(left_tab)):
                row = left_tab[l2]
                for s2 in range(2):
                    if row[s2] == l:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in seen:
                            frontier.append(nctx)
    return list(ctxs.keys())


def _make_blank_aware(tab):
    """Given DFA table (list of rows, row[x] = next state), return True if
    the all-blank tape (always symbol 0) leads to a state from which a halt
    is forced under the machine's transitions.  We approximate: if the blank
    path from state 0 ever reaches a state that has no defined transition on
    some symbol the machine can write, it is suspicious; but the real check is
    done by the kernel.  Here we just require the automaton to accept only
    tapes that can actually appear, which we cannot know a priori.  So we
    accept all DFAs and let the closure decide."""
    return True


def _emit(tm, left_tab, right_tab, ctxs):
    left = [list(row) for row in left_tab]
    right = [list(row) for row in right_tab]
    contexts = [list(c) for c in ctxs]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def _search(tm):
    t, ns, _ = parse(tm)
    # Enumerate DFAs for the left half-tape with 1..3 states, BFS-canonical.
    # State 0 loops on symbol 0 (blank far away).
    # We build tables as list of rows; row[x] in 0..n-1.
    import itertools

    def gen_tables(n):
        # iterate over all functions rows -> for each state i, row[i][0], row[i][1]
        states = list(range(n))
        for combo in itertools.product(states, repeat=2 * n):
            tab = []
            ok = True
            for i in range(n):
                r0 = combo[2 * i]
                r1 = combo[2 * i + 1]
                if i == 0 and r0 != 0:
                    ok = False
                    break
                tab.append([r0, r1])
            if ok:
                yield tab

    # Try pair of identical DFAs first (symmetric machines), then all pairs.
    tables_by_n = {}
    for n in (1, 2, 3):
        tables_by_n[n] = list(gen_tables(n))

    for n in (1, 2, 3):
        for lt in tables_by_n[n]:
            for rt in tables_by_n[n]:
                # normalize: use the same n
                if len(lt) != len(rt):
                    continue
                # quick sanity: state 0 blank loop
                if lt[0][0] != 0 or rt[0][0] != 0:
                    continue
                start = (0, 0, 0, 0)
                ctxs = _dfa_closure(tm, lt, rt, start)
                if ctxs is None:
                    continue
                cert = _emit(tm, lt, rt, ctxs)
                if cert is not None:
                    return cert
    return None


NAME = "cps-search-3"


def decide(tm: str):
    try:
        return _search(tm)
    except Exception:
        return None
