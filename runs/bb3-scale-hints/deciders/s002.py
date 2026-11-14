from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Search-based CPS decider.
# For each holdout, enumerate small DFAs for the half-tapes (left reads cells
# left of the head from far away towards the head, right reads cells right of
# the head likewise), build the smallest closed context set for each pair, and
# emit a certificate when the closure contains no halting context.
#
# The hints say survivors are counters/bouncers, so plain n-gram windows are
# useless; we enumerate automata of growing size instead and prune early: any
# automaton that cannot even represent the blank tape is rejected, and any
# partial table where a symbol that can lead to a halt would force the blank
# tape to be in the halting set is pruned.  For a surviving DFA the other side
# is reversed/determinized and the closed-context fixpoint is run.

import itertools

def _dfa_states(n):
    return list(range(n))

def _closure(tm, left, right, max_ctx=200000):
    table, n_states, n_symbols = parse(tm)
    # contexts: (l, q, s, r)
    start = (0, 0, 0, 0)
    ctx = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            for (w, mv, q2) in [table.get((q, s))]:
                if w is None:
                    return None
                if mv > 0:
                    l2 = left[l][w]
                    if l2 is None:
                        return None
                    for (r2, s2) in _pairs(right, r):
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            nxt.append(c)
                else:
                    r2 = right[r][w]
                    if r2 is None:
                        return None
                    for (l2, s2) in _pairs(left, l):
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            nxt.append(c)
        frontier = nxt
        if len(ctx) > max_ctx:
            return None
    left_tab = [list(row) for row in left]
    right_tab = [list(row) for row in right]
    contexts = [[a, b, c, d] for (a, b, c, d) in ctx]
    return {"kind": "cps", "left": left_tab, "right": right_tab,
            "contexts": contexts}

def _pairs(aut, state):
    out = []
    for sym in (0, 1):
        nxt = aut[state][sym]
        if nxt is not None:
            out.append((nxt, sym))
    return out

def _minimal_dfa_for_blank(n):
    # build all DFAs on n states where state 0 loops on 0 to itself
    pass

def _enumerate_dfa(n, max_tables=20000):
    # enumerate transition tables with n states, state 0 loops on 0
    # symbols 0,1; each row: (next on 0, next on 1)
    rows = []
    for i in range(n):
        for a in range(n):
            for b in range(n):
                rows.append((a, b))
    for combo in itertools.product(rows, repeat=n):
        tab = [list(r) for r in combo]
        tab[0][0] = 0
        yield [[a, b] for (a, b) in tab]

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # quick run: if it halts we are done
    halted, steps, state, pos, tape = run(tm, 100000)
    if halted:
        return None
    # try 1-state automata first (the hint: state 0 loops on 0)
    for n in (1, 2, 3):
        seen = set()
        for la in _enumerate_dfa(n):
            key = tuple(tuple(r) for r in la)
            if key in seen:
                continue
            seen.add(key)
            # left automaton must accept the blank tape (state 0, all zeros)
            if la[0][0] != 0:
                continue
            # try matching right automaton sizes
            for m in (1, 2, 3):
                for ra in _enumerate_dfa(m):
                    if ra[0][0] != 0:
                        continue
                    cert = _closure(tm, la, ra)
                    if cert is not None:
                        try:
                            from neverhalt.kernel import check
                            check(tm, cert)
                        except Reject:
                            continue
                        return cert
    return None
