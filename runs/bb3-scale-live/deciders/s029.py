from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

import copy
from collections import deque

N_GRAM = 7

def build_ngram_tables(n_states, n_symbols, n_gram):
    # states of the half-tape automaton: tuples of length n_gram of symbols (0/1)
    # 'left' automaton reads cells left of the head towards the head;
    # 'right' automaton reads cells right of the head towards the head.
    # We build them so that state 0 (all-zero half-tape) is index 0.
    # Represent a half-tape state as a tuple (s_{-k}, ..., s_{-1}) for the
    # nearest n_gram cells ordered from far to near.  The automaton reads the
    # next symbol into the state, shifting the window.
    zero = (0,) * n_gram
    idx = {zero: 0}
    order = [zero]
    for a in range(n_symbols):
        for b in range(n_symbols):
            for c in range(n_symbols):
                for d in range(n_symbols):
                    pass
    # generate all tuples of length n_gram over range(n_symbols)
    import itertools
    for tup in itertools.product(range(n_symbols), repeat=n_gram):
        if tup not in idx:
            idx[tup] = len(order)
            order.append(tup)
    n = len(order)
    # transition: state = window (far..near). Reading symbol x (next cell
    # encountered moving towards the head) shifts: new window = (old[1:], x).
    left = [[None] * n_symbols for _ in range(n)]
    right = [[None] * n_symbols for _ in range(n)]
    for tup in order:
        i = idx[tup]
        for x in range(n_symbols):
            nt = (tup[1:] + (x,))
            j = idx.get(nt)
            if j is not None:
                left[i][x] = j
                right[i][x] = j
    return left, right, order, zero

def cps_search(tm, max_steps=200000, max_states=5000, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # try several n-gram sizes
    for ng in range(1, N_GRAM + 1):
        try:
            left, right, order, zero = build_ngram_tables(n_states, n_symbols, ng)
        except Exception:
            continue
        if len(order) > max_states:
            continue
        # BFS over contexts [l, q, s, r], starting from [0,0,0,0]
        zero_i = order.index(zero)
        start = (zero_i, 0, 0, zero_i)
        visited = {start}
        dq = deque([start])
        # precompute closure: for each context we need to expand under every
        # possible incoming symbol from the far side.
        # We'll do a straightforward BFS with a worklist; when a new context
        # is added we mark dirty and re-expand all contexts that can reach it
        # through the required "for EVERY pair" clauses.
        # Simpler: iterate to fixed point.
        changed = True
        while changed and len(visited) <= max_ctx:
            changed = False
            for (l, q, s, r) in list(visited):
                tr = table.get((q, s))
                if tr is None:
                    return None  # halting context -> not a valid closed set
                w, mv, q2 = tr
                if mv > 0:
                    l2 = left[l][w]
                    if l2 is None:
                        continue
                    # for every (r2, s2) with right[r2][s2] == r
                    for r2 in range(len(order)):
                        for s2 in range(n_symbols):
                            if right[r2][s2] == r:
                                ctx = (l2, q2, s2, r2)
                                if ctx not in visited:
                                    visited.add(ctx)
                                    changed = True
                else:
                    r2 = right[r][w]
                    if r2 is None:
                        continue
                    for l2 in range(len(order)):
                        for s2 in range(n_symbols):
                            if left[l2][s2] == l:
                                ctx = (l2, q2, s2, r2)
                                if ctx not in visited:
                                    visited.add(ctx)
                                    changed = True
                if len(visited) > max_ctx:
                    break
        if len(visited) > max_ctx:
            continue
        contexts = [[list(c) for c in ctx] for ctx in visited]
        cert = {
            "kind": "cps",
            "left": left,
            "right": right,
            "contexts": contexts,
        }
        try:
            from neverhalt.kernel import check
            check(tm, cert)
            return cert
        except Exception:
            continue
    return None

def decide(tm: str):
    try:
        return cps_search(tm)
    except Exception:
        return None
