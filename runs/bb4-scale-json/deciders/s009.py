import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "two-color left-anchored n-gram CPS"
# Builds CPS contexts using last-n-cell automata on each half-tape,
# then closes the context set under the kernel's transition rule.
# n=8 is enough to catch the short-period oscillators still remaining
# (the samples above show period-4..8 right/left ping-pong loops).

def build_cps(tm, n):
    table, n_states, n_symbols = parse(tm)
    # left automaton state = tuple of last n cells of left half-tape,
    # read from far away towards the head -> we record them in visit order
    # reversed.  Use a frozenset of strings as state key.
    def refl(x):
        return x if x is not None else None
    # automaton transition: state i --x--> j.  We use int encoding.
    # For last-n-cell memory, state = tuple of n symbols read so far
    # (in reverse visit order, i.e. closest-to-head first).
    def make_aut(n):
        # BFS over reachable states
        start = ()
        trans = {}
        enc = {start: 0}
        frontier = [start]
        while frontier:
            st = frontier.pop()
            i = enc[st]
            for x in (0, 1):
                nxt = (x,) + st[:n-1]
                if nxt not in enc:
                    enc[nxt] = len(enc)
                    frontier.append(nxt)
                trans[(i, x)] = enc[nxt]
        return trans, enc, start

    lt, lenc, lstart = make_aut(n)
    rt, renc, rstart = make_aut(n)
    li = lenc[lstart]
    ri = renc[rstart]
    # contexts: [l, q, s, r]
    ctx = set()
    ctx.add((li, 0, 0, ri))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if len(ctx) > 180000:
                return None
            if (q, s) not in table:
                return None
            w, move, q2 = table[(q, s)]
            if move == 1:
                # right move: l2 = left[l][w] must exist
                if (l, w) not in lt:
                    return None
                l2 = lt[(l, w)]
                for (r2, s2) in rt:
                    if rt[(r2, s2)] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            changed = True
            else:
                if (r, w) not in rt:
                    return None
                r2 = rt[(r, w)]
                for (l2, s2) in lt:
                    if lt[(l2, s2)] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            changed = True
        # encode automata as index lists
    # build left/right tables with nulls
    L = [[None, None] for _ in range(len(lenc))]
    for (i, x), j in lt.items():
        L[i][x] = j
    R = [[None, None] for _ in range(len(renc))]
    for (i, x), j in rt.items():
        R[i][x] = j
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    cert = {"kind": "cps", "left": L, "right": R, "contexts": contexts}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None

def decide(tm):
    for n in (6, 8, 10, 12):
        c = build_cps(tm, n)
        if c is not None:
            return c
    return None
