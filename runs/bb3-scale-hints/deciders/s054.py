from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from collections import deque
from itertools import product

# Shared tables over states A=0, B=1, C=2 etc.
def tbl(tm):
    (table, ns, nsym) = parse(tm)
    out = {}
    for st in range(ns):
        out[st] = {}
        for s in range(nsym):
            t = table.get((st, s))
            if t is not None:
                out[st][s] = t
    return out, ns

# Automaton: list of rows; row[x] = next state or None.
def compose_chain(rows, s):
    cur = 0
    for _ in range(s):
        nx = rows[cur][0]
        if nx is None:
            return None
        cur = nx
    return cur

def find_closing_left(rows, q, s, start_states, right_pairs, trans):
    # BFS over left-automaton states that can reach a context requiring halt.
    # We are given a partial automaton (rows over symbol 0 only in this phase),
    # and we want to know whether from state 0 reading 0 forever we can reach
    # a state l such that the machine in state q, symbol s, does a left move
    # and (if it halts) or requires a specific right state.
    # Simplification: return True if any reachable left state leads (via
    # left-move transition) to a right state that is not 'covered' by the
    # current set of right pairs. We approximate by requiring the left state
    # be 0 only (blank tape invariant) -- handled by the caller.
    return False

def closure_for(rowsL, rowsR, trans, ns):
    # trans: dict (q,s)->(w,move,q2) or None (halt)
    # Find smallest set of contexts [l,q,s,r] closed under the kernel rules.
    # We start from [0,0,0,0] and iterate.
    ctx = set()
    ctx.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            t = trans.get((q, s))
            if t is None:
                # halting context: reject this automaton pair
                return None
            w, move, q2 = t
            if move == 1:
                l2 = rowsL[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with rowsR[r2][s2] == r
                for (r2, s2) in right_pairs:
                    if right_pairs[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            changed = True
            else:
                r2 = rowsR[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in left_pairs:
                    if left_pairs[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            changed = True
    return ctx

def build_cert(tm):
    trans, ns = tbl(tm)
    # Build transition dict.
    tr = {}
    for q in range(ns):
        for s in range(2):
            t = trans[q].get(s)
            if t is None:
                continue
            w, move, q2 = t
            tr[(q, s)] = (w, move, q2)
    # Enumerate small automata over symbol 0 only first (blank tape halves).
    # left[i][0] = j or None.
    # We try pairs of automata up to 3 states per side.
    maxst = 3
    # Precompute right_pairs / left_pairs structure for a given automaton.
    def pairs_of(rows):
        p = {}
        for i in range(len(rows)):
            for x in range(2):
                nx = rows[i][x]
                if nx is not None:
                    p[(i, x)] = nx
        return p
    for nl in range(1, maxst + 1):
        for nr in range(1, maxst + 1):
            # Enumerate automata with states 0..nl-1, state 0 loops on 0.
            # rows[i][x] in {None} U [0,nl)
            for rowsL in _enum_auto(nl):
                for rowsR in _enum_auto(nr):
                    # state 0 must loop on symbol 0
                    if rowsL[0][0] != 0 or rowsR[0][0] != 0:
                        continue
                    lp = pairs_of(rowsL)
                    rp = pairs_of(rowsR)
                    if (0, 0) not in lp or (0, 0) not in rp:
                        continue
                    ctx = closure_for(rowsL, rowsR, tr, ns)
                    if ctx is None:
                        continue
                    if len(ctx) > 200000:
                        continue
                    # Emit certificate.
                    cert = {
                        "kind": "cps",
                        "left": [list(row) for row in rowsL],
                        "right": [list(row) for row in rowsR],
                        "contexts": [list(c) for c in ctx],
                    }
                    return cert
    return None

def _enum_auto(n):
    # rows: list of n rows; row[0], row[1] in [0,n) or None.
    vals = [None] + list(range(n))
    for combo in product(vals, repeat=2 * n):
        rows = []
        ok = True
        for i in range(n):
            rows.append([combo[2 * i], combo[2 * i + 1]])
        yield rows

NAME = "cps_search"

def decide(tm: str):
    try:
        return build_cert(tm)
    except Exception:
        return None
} 