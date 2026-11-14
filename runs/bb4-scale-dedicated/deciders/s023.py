import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

MAX_L = 10
MAX_R = 10
SYM = 2


def state_key(q, s):
    return q * 2 + s


def closure_contexts(table, n_states, n_symbols, left, right, ctx_set, contexts):
    nq = n_states
    nsl = len(left)
    nsr = len(right)
    # map context to index
    idx = {c: i for i, c in enumerate(contexts)}
    frontier = deque(ctx_set)
    while frontier:
        i = frontier.popleft()
        l, q, s, r = contexts[i]
        if q >= nq or s >= n_symbols:
            continue
        tr = table.get((q, s))
        if tr is None:
            continue
        w, mv, q2 = tr
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                continue
            for r2 in range(nsr):
                if right[r2][w] == r:
                    c = (l2, q2, w, r2)
                    if c not in idx:
                        idx[c] = len(contexts)
                        contexts.append(c)
                        frontier.append(len(contexts) - 1)
        else:
            r2 = right[r][w]
            if r2 is None:
                continue
            for l2 in range(nsl):
                if left[l2][w] == l:
                    c = (l2, q2, w, r2)
                    if c not in idx:
                        idx[c] = len(contexts)
                        contexts.append(c)
                        frontier.append(len(contexts) - 1)


def make_cps(table, n_states, n_symbols, left, right):
    nsl = len(left)
    nsr = len(right)
    contexts = [(0, 0, 0, 0)]
    ctx_set = {contexts[0]}
    closure_contexts(table, n_states, n_symbols, left, right, ctx_set, contexts)
    if len(contexts) > 200000:
        return None
    # check no halting context
    for c in contexts:
        l, q, s, r = c
        tr = table.get((q, s))
        if tr is None:
            return None
    left_t = [[left[i][x] for x in range(n_symbols)] for i in range(nsl)]
    right_t = [[right[i][x] for x in range(n_symbols)] for i in range(nsr)]
    contexts_t = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left_t, "right": right_t, "contexts": contexts_t}


def prune_left(tr, halting_ctx):
    # If adding transitions forces the blank tape to be accepting (i.e. we can
    # reach a halting context from the blank tape), prune.
    pass


def enumerate_dfas(limit):
    # BFS-canonical DFA enumeration over {0,1} with state 0 looping on 0.
    # state 0 transitions: delta[0][0] = 0. delta[0][1] can be 0..limit-1.
    # Canonical: states introduced in order, transitions lead only to
    # existing or next-introduced states (in canonical BFS order).
    seen = set()
    results = []
    # represent DFA as tuple of tuples
    def canon(d):
        # BFS rename from state 0
        n = len(d)
        if n == 0:
            return ()
        new = {}
        order = []
        dq = [0]
        new[0] = 0
        order.append(0)
        while dq:
            u = dq.pop(0)
            for x in range(SYM):
                v = d[u][x]
                if v not in new:
                    new[v] = len(order)
                    order.append(v)
                    dq.append(v)
        nd = len(order)
        if nd > limit:
            return None
        out = []
        for i in range(nd):
            row = []
            for x in range(SYM):
                v = d[new_inv(order[i])][x] if False else None
                row.append(v)
            out.append(tuple(row))
        return tuple(out)
    # simpler: generate incrementally
    def gen():
        # states 0..k-1, canonical: 0 loops on 0
        # delta[0][0] = 0. delta[0][1] = 0 or 1 (if k>1)
        # We generate all DFAs with k states where state 0 is initial and
        # reachable from 0 (so all states reachable).
        # BFS canonical: transitions of new state i lead to states <= i+1,
        # and if they lead to i+1 it must be the first occurrence.
        # Enumerate recursively.
        for k in range(1, limit + 1):
            # assign transitions one state at a time
            rows = []
            def rec(i, used):
                if i == k:
                    # canonical: state 0 initial, all reachable implied by
                    # transitions to existing states only
                    d = tuple(tuple(r) for r in rows)
                    if d not in seen:
                        seen.add(d)
                        results.append(d)
                    return
                if i == 0:
                    # delta[0][0] = 0
                    rows.append((0, None))
                    # delta[0][1] can be 0 or 1 (if k>1)
                    if k == 1:
                        rows[0] = (0, 0)
                        rec(1, used)
                        rows.pop()
                    else:
                        rows[0] = (0, 0)
                        rec(1, used)
                        rows[0] = (0, 1)
                        rec(1, used)
                        rows.pop()
                else:
                    # state i: delta[i][0] and delta[i][1] in 0..i (can also
                    # go to i? no self loops allowed for canonical? Actually
                    # allow 0..i, but canonical requires first occurrence of
                    # new state j at j: transitions to j only from states
                    # <= j-1 when j is introduced. For simplicity allow
                    # 0..i and dedupe via seen.
                    for a in range(i + 1):
                        for b in range(i + 1):
                            rows.append((a, b))
                            rec(i + 1, used)
                            rows.pop()
            rec(0, set())
    gen()
    return results


def build_halting_set(table, n_states, n_symbols):
    # contexts that can reach a halting transition
    # we just compute set of (q,s) that halt directly or via transitions
    halt = set()
    work = deque()
    for (q, s), tr in table.items():
        if tr is None:
            continue
        w, mv, q2 = tr
    # direct halting transitions are absent from table
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                halt.add((q, s))
    # backwards closure
    changed = True
    while changed:
        changed = False
        for (q, s), tr in list(table.items()):
            w, mv, q2 = tr
            if (q2, w) in halt:
                if (q, s) not in halt:
                    halt.add((q, s))
                    changed = True
    return halt


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    # Precompute halting contexts
    halt = build_halting_set(table, n_states, n_symbols)
    if not halt:
        return None
    dfas = enumerate_dfas(MAX_L)
    for L in dfas:
        # L is tuple of rows, row = (delta[0], delta[1])
        # build left automaton with len(L) states
        left = [list(r) for r in L]
        # ensure state 0 loops on 0
        if left[0][0] != 0:
            continue
        # quick necessary condition: blank tape (state 0) must not be able
        # to reach a halting symbol context. We approximate by checking
        # whether any context (0, q, s, 0) with (q,s) halting is generated.
        # Build right automaton: try all DFAs as right side too.
        for R in enumerate_dfas(MAX_R):
            right = [list(r) for r in R]
            if right[0][0] != 0:
                continue
            cert = make_cps(table, n_states, n_symbols, left, right)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None


if __name__ == "__main__":
    # quick self-test on a known non-halting machine (BB(2) champion halts,
    # so just test parse works)
    print(decide("1RB1LB_1LA---"))
