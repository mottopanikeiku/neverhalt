import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

sys.setrecursionlimit(1000000)

# ---------------------------------------------------------------- utilities

def parse_tm(tm):
    table, ns, nsym = parse(tm)
    return table, ns

def step_state(tm_table, ns, q, s):
    """Return (w, move, q2) or None when the transition halts."""
    try:
        w, mv, q2 = tm_table[(q, s)]
    except KeyError:
        return None
    return w, mv, q2

# ---------------------------------------------------------------- DFA search

def canon_dfa(trans, nstates):
    """Canonical BFS ordering. Returns a tuple of (list of (w0,w1), start) with
    states 0..nstates-1 reachable from 0; None if not all reachable."""
    start = 0
    order = [0]
    seen = {0}
    rows = [None] * nstates
    rows[0] = (trans[0][0], trans[0][1])
    for i in range(len(order)):
        st = order[i]
        for x in (0, 1):
            j = trans[st][x]
            if j is None:
                continue
            if j not in seen:
                if len(order) >= nstates:
                    return None
                seen.add(j)
                order.append(j)
                rows[j] = (trans[j][0], trans[j][1])
    if len(order) != nstates:
        return None
    return tuple(rows)

def enumerate_dfas(nstates, cap=8):
    """Enumerate canonical DFAs of exactly nstates states.  State 0 loops on 0
    (the blank half-tape).  Yields (rows, nstates)."""
    if nstates > cap:
        return
    rng = range(nstates)
    # DFS over transition tables, canonicalised: BFS reachable set must be all.
    # To keep it small we require state 0 -> 0 on symbol 0.
    import itertools
    # Represent rows as pairs (t0, t1).
    # Enumerate all functions for each state, then canonicalise by BFS order.
    rows = [None] * nstates
    def rec(i):
        if i == nstates:
            # canonicalise
            c = canon_dfa(rows, nstates)
            if c is not None:
                yield c
            return
        for t0 in rng:
            for t1 in rng:
                if i == 0 and t0 != 0:
                    continue
                rows[i] = (t0, t1)
                yield from rec(i + 1)
    yield from rec(0)

# ---------------------------------------------------------------- closure

def closure_contexts(tm_table, ns, left, right, max_ctx=200000):
    """Smallest closed context set for the given pair of automata.
    left/right: lists of (t0, t1) indexed by state.
    Returns (contexts, has_halt) or None if too big."""
    # context: (l, q, s, r)
    init = (0, 0, 0, 0)
    seen = {init}
    frontier = [init]
    while frontier:
        if len(seen) > max_ctx:
            return None
        nxt = []
        for (l, q, s, r) in frontier:
            tr = step_state(tm_table, ns, q, s)
            if tr is None:
                return None  # halting context -> not closed
            w, mv, q2 = tr
            if mv > 0:
                # right move: push w onto left half-tape
                l2 = left[l][w]
                if l2 is None:
                    return None
                # pop nearest cell s2 off right half-tape: for every pair
                # (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    row = right[r2]
                    for s2 in (0, 1):
                        if row[s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                nxt.append(ctx)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    row = left[l2]
                    for s2 in (0, 1):
                        if row[s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in seen:
                                seen.add(ctx)
                                nxt.append(ctx)
        frontier = nxt
    return seen, False

# ---------------------------------------------------------------- main

def decide(tm):
    tm_table, ns = parse_tm(tm)
    if ns > 4:
        return None
    # small search: 1..4 states per side
    for nleft in range(1, 5):
        for nright in range(1, 5):
            found = False
            for left in enumerate_dfas(nleft):
                for right in enumerate_dfas(nright):
                    res = closure_contexts(tm_table, ns, left, right)
                    if res is None:
                        continue
                    ctxs, _ = res
                    # emit certificate
                    cert = {
                        "kind": "cps",
                        "left": [[list(row) for row in left]],
                        "right": [[list(row) for row in right]],
                        "contexts": [[l, q, s, r] for (l, q, s, r) in ctxs],
                    }
                    # left/right must be indexed tables: kernel expects
                    # left[i][x] = state or null.  Our rows are (t0,t1) tuples.
                    cert["left"] = [[row[0], row[1]] for row in left]
                    cert["right"] = [[row[0], row[1]] for row in right]
                    # state 0 must loop on symbol 0
                    if cert["left"][0][0] == 0 and cert["right"][0][0] == 0:
                        return cert
                    found = True
            if found:
                break
        if found:
            break
    return None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    print(decide(tm))
