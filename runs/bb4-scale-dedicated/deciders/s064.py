import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- basic helpers ----------

def table_of(tm):
    tbl, ns, nsym = parse(tm)
    # tbl[(state, symbol)] = (write, move, next) ; halting transitions absent
    return tbl, ns, nsym

def is_halting(tbl, q, s):
    return (q, s) not in tbl

# ---------- context-set computation ----------
#
# contexts are tuples (l, q, s, r).  left/right are transition tables:
#   left[i][x] = next state or None ; left[0][0] == 0 required.
# We compute the smallest closed set containing the initial context
# [0,0,0,0] (machine starts in state 0 = A on a blank tape).

def closure(left, right, nq, nsym, limit=200000):
    init = (0, 0, 0, 0)
    if init not in _ctx_key(left, right, nq, nsym):
        pass
    ctxs = {init}
    frontier = [init]
    # precompute reverse maps
    lrev = {}
    for i in range(len(left)):
        for x in range(nsym):
            j = left[i][x]
            if j is not None:
                lrev.setdefault(j, []).append((i, x))
    rrev = {}
    for i in range(len(right)):
        for x in range(nsym):
            j = right[i][x]
            if j is not None:
                rrev.setdefault(j, []).append((i, x))
    while frontier:
        if len(ctxs) > limit:
            return None
        nxt = []
        for (l, q, s, r) in frontier:
            # machine transition
            tr = _M[(q, s)]
            if tr is None:
                # halting context -> closure is not halting-free
                return None
            w, mv, q2 = tr
            if mv == 1:
                # right move: l2 = left[l][w]; r2,s2 with right[r2][s2]==r
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in rrev.get(r, ()):
                    c = (l2, q2, s2, r2)
                    if c not in ctxs:
                        ctxs.add(c)
                        nxt.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in lrev.get(l, ()):
                    c = (l2, q2, s2, r2)
                    if c not in ctxs:
                        ctxs.add(c)
                        nxt.append(c)
        frontier = nxt
    return ctxs

def _ctx_key(*a):
    return a

# ---------- DFA enumeration ----------

def enumerate_dfa_states(max_states):
    """Yield transition tables for deterministic automata with n states,
    state 0 loops on symbol 0 (blank tape representation)."""
    # BFS-canonical-ish enumeration: all functions [n][2] -> [n] with
    # row 0 = (0,0) fixed.
    for n in range(1, max_states + 1):
        rows = [tuple([0, 0])]  # state 0 fixed
        others = list(range(n))
        # enumerate remaining rows
        from itertools import product
        for combo in product(range(n), repeat=2 * (n - 1)):
            t = [rows[0]]
            for i in range(n - 1):
                t.append((combo[2 * i], combo[2 * i + 1]))
            yield t

# ---------- emit certificate ----------

def make_cert(left, right, nq, ctxs):
    return {
        "kind": "cps",
        "left": [list(row) for row in left],
        "right": [list(row) for row in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in ctxs],
    }

# ---------- main decider ----------

NAME = "cps-search"

def decide(tm):
    global _M, _Q
    tbl, ns, nsym = table_of(tm)
    if nsym != 2:
        return None
    _M = tbl
    _Q = ns
    best = None
    # try small automata first
    for max_states in (1, 2, 3, 4, 5):
        for left in enumerate_dfa_states(max_states):
            # quick sanity: left[0][0] == 0 by construction
            for max_states_r in (1, 2, 3, 4, 5):
                if max_states_r > max_states:
                    continue
                for right in enumerate_dfa_states(max_states_r):
                    ctxs = closure(left, right, ns, nsym, limit=200000)
                    if ctxs is not None:
                        cert = make_cert(left, right, ns, ctxs)
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None

# ---------- module-level init for speed ----------

_M = None
_Q = None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    print(c)
