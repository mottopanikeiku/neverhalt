import sys
sys.setrecursionlimit(100000)
from neverhalt.tm import parse

NAME = "dfa-search-2"

HALT = object()

def build_tables(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

def decide(tm):
    try:
        table, n_states, n_symbols = build_tables(tm)
    except Exception:
        return None
    syms = list(range(n_symbols))

    # Forward halting reachability of abstract (q, s) pairs.
    # A context halts if some (q,s) pair can reach a halting transition.
    # We search automata (state0 = blank tape loops on 0).
    # Because the search space is large we use a bounded enumeration.
    nA = n_states
    # Enumerate automata as tuples of (transitions per state over syms),
    # state 0 must map 0 -> 0. We generate all tables with nA states where
    # state 0 loops on symbol 0, other entries arbitrary but we keep small
    # alphabets by allowing None (dead) transitions.
    # To keep the search finite, we restrict to automata of size 1..3 states,
    # all states reachable, state 0 loops on 0.
    # We try all possible left automata with 1..3 states.
    # For the right side, we derive constraints: for a context (l,q,s,r),
    # moving right requires left[l][w] defined and for every (r2,s2) with
    # right[r2][s2]==r the new context must exist.  We instead close the
    # context set as a fixpoint.

    # Precompute halting transitions: (q,s) that halt.
    halting = set()
    for q in range(nA):
        for s in syms:
            if (q, s) not in table:
                halting.add((q, s))

    # We enumerate left automata with nL states (1..3) where state 0 loops 0.
    # right automata similarly, but to limit search we enumerate both and
    # close contexts.
    # To make this practical, we first try symmetric n-gram automata.
    for nhalf in range(1, 4):
        # ngram automaton for one side: state 0..2^n - 1 representing the last
        # n cells read so far (far to head order).  State 0 = all blank.
        # left[i][x]: new state after reading x, i.e. shift window.
        size = 1 << nhalf
        ngram = [[0]*n_symbols for _ in range(size)]
        for i in range(size):
            for x in syms:
                # window bits: bit0 is the most recent (nearest head)?
                # We define state as tuple of cells read so far, oldest first.
                # Reading x appends: new = ((i << 1) | x) mod 2^n, but cap to
                # the n most recent: shift left and drop oldest.
                new = ((i << 1) | x) & (size - 1)
                ngram[i][x] = new
        # Try pairs of ngram automata with different sizes per side.
        for nR in range(1, 4):
            sizeR = 1 << nR
            ngramR = [[0]*n_symbols for _ in range(sizeR)]
            for i in range(sizeR):
                for x in syms:
                    new = ((i << 1) | x) & (sizeR - 1)
                    ngramR[i][x] = new
            cert = close_contexts(table, nA, n_symbols, ngram, ngramR)
            if cert is not None:
                return cert
    return None

def close_contexts(table, nA, n_symbols, left, right):
    nL = len(left)
    nR = len(right)
    # Start with [0,0,0,0]
    ctxs = set()
    ctxs.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctxs):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
            else:
                # halting transition: reject
                return None
            if move == 1:
                l2 = left[l][w] if w < n_symbols else None
                if l2 is None:
                    return None
                # For every (r2,s2) with right[r2][s2]==r, need context
                # (l2, q2, s2, r2).
                for r2 in range(nR):
                    for s2 in range(n_symbols):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctxs:
                                ctxs.add(c)
                                changed = True
            else:
                r2 = right[r][w] if w < n_symbols else None
                if r2 is None:
                    return None
                for l2 in range(nL):
                    for s2 in range(n_symbols):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctxs:
                                ctxs.add(c)
                                changed = True
    if len(ctxs) > 200000:
        return None
    # Build certificate
    def mk(left_t, right_t):
        lt = [[left_t[i][x] for x in range(n_symbols)] for i in range(len(left_t))]
        rt = [[right_t[i][x] for x in range(n_symbols)] for i in range(len(right_t))]
        return lt, rt
    lt, rt = mk(left, right)
    contexts = [[list(c) for c in ctxs]]
    return {"kind": "cps", "left": lt, "right": rt, "contexts": contexts}