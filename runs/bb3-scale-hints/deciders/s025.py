import sys
sys.setrecursionlimit(1000000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

S = 2


def make_tables(tm):
    table, n_states, _ = parse(tm)
    return table, n_states


def build_halting_contexts(table, n_states):
    # contexts are (q, s) pairs that transition to a halting transition
    hal = set()
    for q in range(n_states):
        for s in range(S):
            if (q, s) not in table:
                hal.add((q, s))
    return hal


def enumerate_dfa(nstates):
    # enumerate deterministic automata on S symbols, states 0..nstates-1,
    # state 0 loops on 0 and maps 0 -> 0
    results = []
    # transitions: for each state, for each symbol, target or None
    choices = [range(nstates) for _ in range(nstates)] + [None] * nstates

    def rec(state, syms):
        if state == nstates:
            # check states reachable and canonical: state 0 -> 0 on 0
            # build table
            tbl = [[None] * S for _ in range(nstates)]
            idx = 0
            for st in range(nstates):
                for sy in range(S):
                    if sy == 0 and st == 0:
                        tbl[st][sy] = 0
                    else:
                        v = choices[idx]
                        idx += 1
                        tbl[st][sy] = v
            # skip if unreachable states (canonical BFS)
            seen = {0}
            frontier = [0]
            while frontier:
                nxt = []
                for st in frontier:
                    for sy in range(S):
                        t = tbl[st][sy]
                        if t is not None and t not in seen:
                            seen.add(t)
                            nxt.append(t)
                frontier = nxt
            if len(seen) != nstates:
                return
            results.append(tbl)
            return
        rec(state + 1, syms)

    # simpler: recursive enumeration
    tables = []

    def rec2(state):
        if state == nstates:
            tbl = [[None] * S for _ in range(nstates)]
            tbl[0][0] = 0
            for st in range(1, nstates):
                for sy in range(S):
                    tbl[st][sy] = None
            # rebuild from list
            return
        for sy in range(S):
            if sy == 0 and state == 0:
                continue
            for target in list(range(nstates)) + [None]:
                pass
        return

    # instead use product recursion via index
    total = (nstates + 1) ** (nstates * S - 1)
    for code in range(total):
        c = code
        tbl = [[None] * S for _ in range(nstates)]
        tbl[0][0] = 0
        ok = True
        for st in range(nstates):
            for sy in range(S):
                if st == 0 and sy == 0:
                    continue
                v = c % (nstates + 1)
                c //= (nstates + 1)
                if v == nstates:
                    tbl[st][sy] = None
                else:
                    tbl[st][sy] = v
        # canonical: BFS from 0 must cover all states
        seen = {0}
        frontier = [0]
        while frontier:
            nxt = []
            for st in frontier:
                for sy in range(S):
                    t = tbl[st][sy]
                    if t is not None and t not in seen:
                        seen.add(t)
                        nxt.append(t)
            frontier = nxt
        if len(seen) != nstates:
            continue
        # canonical numbering: BFS order from 0
        order = []
        seen = {0}
        frontier = [0]
        while frontier:
            nxt = []
            for st in frontier:
                order.append(st)
                for sy in range(S):
                    t = tbl[st][sy]
                    if t is not None and t not in seen:
                        seen.add(t)
                        nxt.append(t)
            frontier = nxt
        # remap
        remap = {}
        for i, st in enumerate(order):
            remap[st] = i
        newtbl = [[None] * S for _ in range(nstates)]
        for st in range(nstates):
            for sy in range(S):
                t = tbl[st][sy]
                newtbl[remap[st]][sy] = remap[t] if t is not None else None
        # dedupe
        key = tuple(tuple(r) for r in newtbl)
        if key not in tables:
            tables.append(key)
    return tables


def left_delta(tbl, l, w):
    return tbl[l][w]


def right_delta(tbl, r, w):
    return tbl[r][w]


def closed_contexts(table, n_states, left_tbl, right_tbl):
    # contexts: set of (l, q, s, r)
    ctx = set()
    # start: [0,0,0,0] if valid
    if left_tbl[0][0] is not None and right_tbl[0][0] is not None:
        ctx.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if (q, s) not in table:
                return None
            w, move, q2 = table[(q, s)]
            if move > 0:
                l2 = left_tbl[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with right_tbl[r2][s2] == r
                for r2 in range(len(right_tbl)):
                    for s2 in range(S):
                        if right_tbl[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                changed = True
            else:
                r2 = right_tbl[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left_tbl)):
                    for s2 in range(S):
                        if left_tbl[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                changed = True
    return ctx


def cert_from_contexts(table, n_states, left_tbl, right_tbl, ctx):
    # ensure no halting context
    for (l, q, s, r) in ctx:
        if (q, s) not in table:
            return None
    left = [[None] * S for _ in range(len(left_tbl))]
    right = [[None] * S for _ in range(len(right_tbl))]
    for i in range(len(left_tbl)):
        for x in range(S):
            left[i][x] = left_tbl[i][x]
    for i in range(len(right_tbl)):
        for x in range(S):
            right[i][x] = right_tbl[i][x]
    contexts = [[l, q, s, r] for (l, q, s, r) in sorted(ctx)]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm: str) -> dict | None:
    table, n_states = make_tables(tm)
    # small optimizations: try automata sizes 1..4 for each side independently
    # but the closure needs both.
    for nL in range(1, 5):
        lefts = enumerate_dfa(nL)
        if nL == 1:
            lefts = [lefts[0]] if lefts else []
        for nR in range(1, 5):
            rights = enumerate_dfa(nR)
            if nR == 1:
                rights = [rights[0]] if rights else []
            for L in lefts:
                for R in rights:
                    ctx = closed_contexts(table, n_states, L, R)
                    if ctx is None:
                        continue
                    # check for halting contexts
                    bad = False
                    for (l, q, s, r) in ctx:
                        if (q, s) not in table:
                            bad = True
                            break
                    if bad:
                        continue
                    cert = cert_from_contexts(table, n_states, L, R, ctx)
                    if cert is not None:
                        return cert
    return None
