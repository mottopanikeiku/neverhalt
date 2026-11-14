import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "dfa_reduction"

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
        n = n_states
        # state index 0 = A; halting transitions are absent
        # enumerate DFAs for one half-tape in BFS-canonical order
        # we build the DFA offline: it reads symbols from far away towards head
        # state 0 is all-blank half-tape
        # We need: for every context [l,q,s,r] the step rules hold.
        # Here we enumerate DFA tables for the left half-tape of size up to K,
        # with left[0][0] == 0, and compute the minimal closed context set
        # together with the right half-tape DFA determined by the closure.
        # Simpler robust approach: enumerate small DFAs for BOTH sides directly.
        # A right-half DFA is read from far away towards head as well.
        # We accept a pair of DFAs (L, R) if the closed-context fixpoint
        # starting from [0,0,0,0] yields a set with no halting context.
        K = 4  # states per side
        # enumerate DFA transition tables: for each state 0..K-1, for each symbol
        # 0..n_symbols-1, either a next state in 0..K-1 or None.
        # restrict: left[0][0] == 0, right[0][0] == 0 (all-blank half-tape loops)
        import itertools
        choices = [list(range(K)) + [None]]
        # count: for K=4, (4+1)^8 per automaton -> too many.
        # Instead do BFS-canonical enumeration of reachable DFAs.
        def enum_dfas(K):
            # canonical: enumerate reachable subsets via BFS on transition tables
            # Represent table as tuple of K*n_symbols entries (state index or -1).
            # Start with all-blank state 0 looping on 0; other entries may be anything.
            # We generate tables reachable by starting from a seed and expanding.
            # Simpler: enumerate all tables where each state's transitions are
            # canonicalized by BFS order of discovery.
            results = []
            # canonical BFS: assign next states in order 0..K-1 by discovery
            # We enumerate trees of reachable states.
            # Do iterative deepening on number of used states.
            def rec(assign, used, next_state, tables):
                # assign: dict (state,sym) -> next or None
                # used: set of states
                if next_state == K:
                    # check canonical: used must be exactly {0..m-1} for m=len(used)
                    m = len(used)
                    if used != set(range(m)):
                        return
                    results.append(assign.copy())
                    return
                # decide transitions for state next_state
                # to keep canonical, allow None or states < K (any)
                # We'll try None first, then states 0..K-1
                opts = [None] + list(range(K))
                for sym in range(1):  # only symbol 0 matters for blank loop restriction? symbols are 0/1
                    pass
                # enumerate per symbol; but to limit, require state 0 loops on 0
                if next_state == 0:
                    assign[(0,0)] = 0
                    rec(assign, used, next_state+1, tables)
                    return
                for v in opts:
                    assign[(next_state,0)] = v
                    used2 = used | ({v} if v is not None else set())
                    # canonical: new states must be numbered in increasing order
                    if v is not None and v >= K:
                        continue
                    # require states appear in canonical BFS order: at step, v must be <= next_state+1
                    if v is not None and v > next_state:
                        continue
                    rec(assign, used2, next_state+1, tables)
            # We'll just enumerate a limited set of small DFAs with states 0..K-1
            # and all transitions arbitrary, but canonicalize by renaming.
            return results
        # This enumeration is expensive; instead directly build candidate DFAs
        # that "remember the last n cells": shift registers.
        def shift_dfa(n_cells):
            # state = tuple of last n_cells bits (read from far away towards head,
            # i.e. the sequence of cells encountered so far)
            # state 0 = all blank
            states = {}
            def st(seq):
                return seq
            # build table: state = tuple, next on symbol x = (state + (x,))[-n_cells:]
            table = {}
            cur = 0
            q = 0
            seen = {}
            def idx(seq):
                if seq not in seen:
                    seen[seq] = len(seen)
                return seen[seq]
            # enumerate reachable sequences
            frontier = [()]
            seen_seq = {(): 0}
            order = [()]
            i = 0
            while i < len(order):
                seq = order[i]
                i += 1
                for x in range(n_symbols):
                    ns = (seq + (x,))[-n_cells:] if n_cells > 0 else ()
                    if ns not in seen_seq:
                        seen_seq[ns] = len(order)
                        order.append(ns)
            m = len(order)
            tab = [[None]*n_symbols for _ in range(m)]
            base = (0,)*n_cells
            for si, seq in enumerate(order):
                for x in range(n_symbols):
                    ns = (seq + (x,))[-n_cells:]
                    tab[si][x] = seen_seq[ns]
            return tab, m
        # Try shift-register DFAs of sizes 1..4 on both sides.
        for ncl in range(0, 5):
            L, ml = shift_dfa(ncl)
            R, mr = shift_dfa(ncl)
            cert = closed_context(L, R, n, ml, mr)
            if cert:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
        return None

def closed_context(L, R, n, ml, mr):
    # contexts: [l, q, s, r]
    # start with [0,0,0,0]
    contexts = set()
    contexts.add((0,0,0,0))
    changed = True
    while changed:
        changed = False
        newc = set()
        for (l,q,s,r) in contexts:
            trans = table_global.get((q,s))
            if trans is None:
                continue
            w, move, q2 = trans
            if move == 1:
                # right move: l2 = L[l][w]; need [l2,q2,s2,r2] for all r2 with R[r2][s2]==r
                if L[l][w] is None:
                    return None
                l2 = L[l][w]
                for r2 in range(mr):
                    for s2 in range(2):
                        if R[r2][s2] == r:
                            c = (l2,q2,s2,r2)
                            if c not in contexts:
                                newc.add(c)
            else:
                if R[r][w] is None:
                    return None
                r2 = R[r][w]
                for l2 in range(ml):
                    for s2 in range(2):
                        if L[l2][s2] == l:
                            c = (l2,q2,s2,r2)
                            if c not in contexts:
                                newc.add(c)
        if newc:
            contexts |= newc
            changed = True
    # check no context halts: all (q,s) present must have transitions
    for (l,q,s,r) in contexts:
        if (q,s) not in table_global:
            return None
    # build certificate
    left = [[None]*2 for _ in range(ml)]
    for i in range(ml):
        for x in range(2):
            left[i][x] = L[i][x]
    right = [[None]*2 for _ in range(mr)]
    for i in range(mr):
        for x in range(2):
            right[i][x] = R[i][x]
    ctxs = [[l,q,s,r] for (l,q,s,r) in contexts]
    if len(ctxs) > 200000 or ml > 5000 or mr > 5000:
        return None
    return {"kind":"cps","left":left,"right":right,"contexts":ctxs}

table_global = {}
