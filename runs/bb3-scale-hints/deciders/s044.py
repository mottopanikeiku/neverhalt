from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

# Search for CPS certificates for holdout machines.
# Strategy: enumerate small DFAs for the left half-tape, build the right side
# automaton by reverse-determinization, and run the closed-context fixpoint.
# Only emit certificates that the kernel accepts.

def _build_automaton(n_states, trans):
    return [[trans.get((i, x)) for x in (0, 1)] for i in range(n_states)]

def _closure_contexts(left, right, n_states_machine, n_symbols, table, trans, quota=200000):
    # BFS-canonical DFA enumeration is done in the caller. Here we compute the
    # closed context set from a candidate (left, right) pair and the machine's
    # transition table. Return the list of contexts or None if a halting
    # context is forced.
    ctx = set()
    start = (0, 0, 0, 0)
    if start not in ctx:
        ctx.add(start)
    stack = [start]
    while stack:
        l, q, s, r = stack.pop()
        if (q, s) not in table:
            return None  # halting context forced
        w, move, q2 = table[(q, s)]
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            stack.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            stack.append(c)
        if len(ctx) > quota:
            return None
    return sorted(ctx)

def _canonical_dfa_table(n_states):
    # Enumerate all transition tables of n_states states over {0,1}, requiring
    # state 0 loops on symbol 0, and BFS-canonical numbering starting at 0.
    # Yields (n_states, transitions list of (i, x, j)).
    # Simple enumeration for n_states <= 3 is enough for this round.
    import itertools
    idx = list(itertools.product(range(n_states), repeat=(n_states * 2)))
    for vals in idx:
        ok = True
        for i in range(n_states):
            for x in (0, 1):
                ok = ok  # placeholder, checked below
        # state 0 loops on 0
        if vals[0] != 0:
            continue
        trans = []
        for i in range(n_states):
            for x in (0, 1):
                trans.append((i, x, vals[i * 2 + x]))
        # BFS-canonical check
        seen = {0}
        frontier = [0]
        nxt = 1
        while frontier and nxt < n_states:
            newf = []
            for u in frontier:
                for x in (0, 1):
                    v = vals[u * 2 + x]
                    if v not in seen:
                        seen.add(v)
                        newf.append(v)
            frontier = newf
            nxt += 1
        if len(seen) != n_states:
            continue
        # Require canonical numbering: state 0 -> 0 on 0, and BFS order.
        # We just require that the first time a state appears in BFS it gets
        # the next number.
        order = []
        seen2 = set()
        frontier = [0]
        order.append(0)
        seen2.add(0)
        while frontier:
            newf = []
            for u in frontier:
                for x in (0, 1):
                    v = vals[u * 2 + x]
                    if v not in seen2:
                        seen2.add(v)
                        order.append(v)
                        newf.append(v)
            frontier = newf
        # canonical: order must be exactly [0,1,...] i.e. BFS discovery order
        # must match numeric labels.
        if order != list(range(n_states)):
            continue
        yield trans

def decide(tm: str) -> dict | None:
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    # Machine states are ints 0..n_states-1; halting transitions are absent.
    # Helper: convert machine transition to (write, move, next).
    # We need a bound on machine states for context enumeration.
    # Try the machine's own state count for a quick pass, then a few extra.
    import sys
    sys.setrecursionlimit(10000)
    # First, try small automata: 1, 2, 3 states per side.
    for n_left in (1, 2, 3):
        for n_right in (1, 2, 3):
            # Enumerate left automata
            for lt in _canonical_dfa_table(n_left):
                left = [[0, 0] for _ in range(n_left)]
                for (i, x, j) in lt:
                    left[i][x] = j
                # right automaton: start with a guess (all states loop on both)
                # and search over its transitions too.
                for rt in _canonical_dfa_table(n_right):
                    right = [[0, 0] for _ in range(n_right)]
                    for (i, x, j) in rt:
                        right[i][x] = j
                    if left[0][0] != 0 or right[0][0] != 0:
                        continue
                    ctx = _closure_contexts(left, right, n_states, 2, table, None)
                    if ctx is None:
                        continue
                    # Build certificate, trimming transitions not used.
                    used_left = set()
                    used_right = set()
                    for (l, q, s, r) in ctx:
                        used_left.add(l)
                        used_right.add(r)
                    # Kernel requires full automata; we provide them as-is.
                    cert = {
                        "kind": "cps",
                        "left": left,
                        "right": right,
                        "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
                    }
                    try:
                        from neverhalt.kernel import check
                        check(tm, cert)
                        # verified
                        return cert
                    except Reject:
                        pass
                    except Exception:
                        pass
    return None
} 