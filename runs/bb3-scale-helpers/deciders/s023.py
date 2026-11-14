import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# We look for a small pair of half-tape automata (1..3 states per side) whose
# closure contains no halting context for the given machine.  State 0 is the
# all-blank half-tape and must loop on symbol 0.  For every other state we try
# every possible deterministic transition on both symbols (4 choices each),
# then shrink the certificate to exactly the transitions the closure used.

def _small_automata(side):
    # side in 1..3: enumerate all transition tables for `side` states.
    # state 0 loops on 0 (push(blank,0)==blank).
    n = side
    from itertools import product
    # transitions for states 1..n-1 on symbols 0 and 1: each either a state
    # index (0..n-1) or None (never happens).
    opts = [None] + list(range(n))
    for row in product(opts, repeat=2):
        table = {0: (0, 0)}
        for st in range(1, n):
            pass
        yield row

def _build_tables(side):
    from itertools import product
    n = side
    opts = [None] + list(range(n))
    for trans in product(opts, repeat=2):
        # trans = (d_on_0, d_on_1) for state 1 only when side == 2;
        # we handle the general enumeration below.
        break
    # general: for each of states 1..n-1 choose (t0,t1)
    rows = list(product(opts, repeat=2))
    for combo in product(rows, repeat=max(n - 1, 0)):
        table = {0: (0, 0)}
        ok = True
        for i, (t0, t1) in enumerate(combo, start=1):
            if t0 == i and t1 == i:
                # state i loops on both symbols: allowed but useless
                pass
            table[i] = (t0, t1)
        yield table

def _mk_push(table):
    blank = 0
    def push(state, symbol):
        if state not in table:
            return None
        t = table[state][symbol]
        return t
    return push, blank

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # try small left/right automata
    for ls in (1, 2, 3):
        for rs in (1, 2, 3):
            for lt in _build_tables(ls):
                for rt in _build_tables(rs):
                    lp, lb = _mk_push(lt)
                    rp, rb = _mk_push(rt)
                    cert = closure(lp, rp, lb, rb, cap=200000)
                    if cert is None:
                        continue
                    # shrink: keep only transitions used
                    used = set()
                    for (l, q, s, r) in cert.get("contexts", []):
                        for l2 in (lt.get(l) or ()):
                            pass
                    # build minimal tables from used transitions
                    lt2 = {}
                    rt2 = {}
                    for l in set(c[0] for c in cert["contexts"]):
                        for s in (0, 1):
                            nxt = lt.get(l, (None, None))[s] if l in lt else None
                            if nxt is not None:
                                lt2[(l, s)] = nxt
                    for r in set(c[3] for c in cert["contexts"]):
                        for s in (0, 1):
                            nxt = rt.get(r, (None, None))[s] if r in rt else None
                            if nxt is not None:
                                rt2[(r, s)] = nxt
                    # rebuild tables as lists of lists for the kernel
                    nls = max(lt2.keys(), default=(0, 0))[0] + 1 if lt2 else 1
                    nrs = max(rt2.keys(), default=(0, 0))[0] + 1 if rt2 else 1
                    L = [[None, None] for _ in range(nls)]
                    R = [[None, None] for _ in range(nrs)]
                    for (l, s), v in lt2.items():
                        L[l][s] = v
                    for (r, s), v in rt2.items():
                        R[r][s] = v
                    if L[0][0] != 0 or R[0][0] != 0:
                        L[0][0] = 0
                        R[0][0] = 0
                    out = {"kind": "cps", "left": L, "right": R,
                           "contexts": [list(c) for c in cert["contexts"]]}
                    try:
                        check(tm, out)
                    except Reject:
                        continue
                    return out
    return None