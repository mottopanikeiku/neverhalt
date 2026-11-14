from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

import sys
from collections import deque

sys.setrecursionlimit(100000)

NAME = "dfa_search_far_to_head"


def _table(tm):
    return parse(tm)


def _closure_contexts(tm, nstates_l, nstates_r, left, right):
    """Compute the closed context set containing (0,0,0,0).
    Returns (contexts, ok) where ok=False means a halting context is forced.
    """
    table, _, _ = _table(tm)
    ctx = [[0, 0, 0, 0]]
    seen = {(0, 0, 0, 0): True}
    q = deque([(0, 0, 0, 0)])
    while q:
        l, st, s, r = q.popleft()
        if (l, st, s, r) not in seen:
            continue
        if st >= table[0][0] * 0 + len(table):
            # table is dict keyed by (state,symbol); absence means halt
            pass
        key = (st, s)
        if key not in table:
            return None, False  # halting context forced
        w, mv, st2 = table[key]
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None, False
            for (r2, s2) in right_r_pairs:
                if s2 is None:
                    continue
                nkey = (l2, st2, s2, r2)
                if nkey not in seen:
                    seen[nkey] = True
                    ctx.append(list(nkey))
                    q.append(nkey)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None, False
            for (l2, s2) in left_l_pairs:
                if s2 is None:
                    continue
                nkey = (l2, st2, s2, r2)
                if nkey not in seen:
                    seen[nkey] = True
                    ctx.append(list(nkey))
                    q.append(nkey)
    return ctx, True


def _build_pairs(nstates):
    """All (state, symbol) pairs with symbol in {0,1}."""
    return [(i, x) for i in range(nstates) for x in (0, 1)]


def _dfa_for_one_side(tm, max_states, which):
    """Search over DFAs for one half-tape (read far to head).
    Returns list of (states, table) in BFS-canonical order, growing size.
    table[i][x] = next state or None (never happens).
    """
    table, _, _ = _table(tm)
    nsym = 2
    results = []
    for n in range(1, max_states + 1):
        # enumerate all tables with state 0 looping on symbol 0
        import itertools
        # symbol 1 transitions can be any state or None
        choices = []
        for i in range(n):
            if i == 0:
                choices.append([(0, 0)] + [(j,) for j in range(n)] + [(None,)])
            else:
                choices.append([(j,) for j in range(n)] + [(None,)])
        total = 1
        for c in choices:
            total *= len(c)
        if total > 300000:
            total = 300000
        count = 0
        for combo in itertools.product(*choices):
            tab = []
            for i in range(n):
                row = [None, None]
                row[0] = combo[i][0][0]
                row[1] = combo[i][1][0]
                tab.append(row)
            # canonical: no unreachable states
            reach = {0}
            dq = deque([0])
            while dq:
                u = dq.popleft()
                for x in (0, 1):
                    v = tab[u][x]
                    if v is not None and v not in reach:
                        reach.add(v)
                        dq.append(v)
            if len(reach) != n:
                continue
            # build full DFA; map only reachable states
            remap = {}
            newtab = []
            for s in sorted(reach):
                remap[s] = len(remap)
            for s in sorted(reach):
                row = [None, None]
                for x in (0, 1):
                    v = tab[s][x]
                    row[x] = remap.get(v) if v is not None else None
                newtab.append(row)
            m = len(remap)
            results.append((m, newtab))
            count += 1
            if count > 2000:
                break
        if results:
            # dedupe and sort by size
            results = sorted(set((m, tuple(tuple(r) for r in t)) for (m, t) in results))
            results = [(m, [list(r) for r in t]) for (m, t) in results]
        if results:
            break
    return results


_left_l_pairs = None
_right_r_pairs = None


def _try_pair(tm, left, right):
    global _left_l_pairs, _right_r_pairs
    nl = len(left)
    nr = len(right)
    _left_l_pairs = [(i, x) for i in range(nl) for x in (0, 1)]
    _right_r_pairs = [(i, x) for i in range(nr) for x in (0, 1)]
    ctx, ok = _closure_contexts(tm, nl, nr, left, right)
    if not ok:
        return None
    if ctx is None:
        return None
    cert = {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": ctx,
    }
    return cert


def decide(tm):
    # Build DFAs for the left half-tape first (small), then right.
    lefts = _dfa_for_one_side(tm, 3, "left")
    if not lefts:
        return None
    # Try all left DFAs with the canonical right DFA built from the same
    # search but on the other side.
    rights = _dfa_for_one_side(tm, 3, "right")
    if not rights:
        return None
    for (nl, left) in lefts:
        for (nr, right) in rights:
            cert = _try_pair(tm, left, right)
            if cert is not None:
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None
