import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------------------------------------------------------------
# Generic CPS closure builder.
# Left / right automata are given as dicts of dicts with None for
# "never happens" (i.e. the kernel's ``null``).  A context is the
# tuple (l, q, s, r).  We build the smallest closed set containing
# the start context [0,0,0,0] by iterating the kernel's rule.
# ---------------------------------------------------------------

def build_cps(table, n_states, n_symbols, L, R):
    # L: dict state -> dict symbol -> state or None
    # R: same
    start = (0, 0, 0, 0)
    ctx = set()
    ctx.add(start)
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(ctx):
            if q >= n_states or s >= n_symbols:
                return None
            t = table.get((q, s))
            if t is None:
                return None          # halting context -> reject
            w, mv, q2 = t
            if mv == +1:
                l2 = L.get(l, {}).get(w, None)
                if l2 is None:
                    return None
                for r2 in range(len(R)):
                    row = R.get(r2)
                    if row is None:
                        continue
                    for s2 in range(n_symbols):
                        if row.get(s2, None) == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                changed = True
            else:  # mv == -1
                r2 = R.get(r, {}).get(w, None)
                if r2 is None:
                    return None
                for l2 in range(len(L)):
                    row = L.get(l2)
                    if row is None:
                        continue
                    for s2 in range(n_symbols):
                        if row.get(s2, None) == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                changed = True
    if len(ctx) > 200000:
        return None
    left = [[L.get(i, {}).get(x) for x in range(n_symbols)] for i in range(len(L))]
    right = [[R.get(i, {}).get(x) for x in range(n_symbols)] for i in range(len(R))]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}


def canon_grow(L, R, n_states, n_symbols):
    """Try every pair of automata with at most `n_states` states per side,
    where state 0 loops on every symbol it is defined for and the tables
    are row-major strings of small ints / -1.  Return the first working
    certificate or None."""
    import itertools
    # candidate row encodings: for each state a tuple of target states,
    # one per symbol, entries in [0, n_states-1] or -1 (must never happen).
    # Restrict: state 0 must loop on symbol 0 (as hinted).
    def rows_for(n):
        # generate all rows lazily
        out = []
        for row in itertools.product(range(n + 1), repeat=n_symbols):
            out.append(row)
        return out

    # We search in order: automata sizes 0..n_states (0 = no states).
    # For efficiency, precompute row lists once per size.
    maxr = n_states + 1
    allrows = [rows_for(k) for k in range(maxr)]

    for nl in range(1, maxr):
        Lrows = allrows[nl]
        for L in itertools.product(Lrows, repeat=nl):
            # enforce state 0 loops on symbol 0
            if L[0][0] != 0:
                continue
            for nr in range(1, maxr):
                Rrows = allrows[nr]
                for R in itertools.product(Rrows, repeat=nr):
                    if R[0][0] != 0:
                        continue
                    for q in range(n_states):
                        for s in range(n_symbols):
                            pass
                    # try this pair on every caller machine?  Too slow per
                    # machine; the caller supplies the machine and we only
                    # need one certificate.  We defer the actual closure
                    # to the caller because it needs the table.
                    yield L, R


# ---------------------------------------------------------------
# Decider entry point.
# ---------------------------------------------------------------

DECIDER_NAME = "cps_search"

def decide(tm: str):
    table, n_states, n_symbols = parse(tm)
    # 1) small n-gram automata first (fast, often enough)
    for ng in range(1, 4):
        # state = last ng cells, read far-to-head
        n = 2 ** ng
        if n > 6:
            break
        def mk(n, ng):
            # states are bitmasks of the last ng cells; automaton reads
            # new cell from far side, shifts it in at the far end.
            L = {}
            R = {}
            for i in range(n):
                for x in range(2):
                    # we do not know the automaton semantics for arbitrary
                    # symbols in general; for n-gram we define:
                    # state = value of cells; new symbol x arrives at the
                    # far side, so it becomes the new low bit and the
                    # highest bit is dropped.  This is the standard
                    # n-gram DFA for the machine's own half-tape.
                    j = ((i << 1) | x) & (n - 1)
                    L.setdefault(i, {}).setdefault(x, j)
                    R.setdefault(i, {}).setdefault(x, j)
            return L, R
        L, R = mk(n, ng)
        cert = build_cps(table, n_states, n_symbols, L, R)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass

    # 2) search over small automata, growing sizes.  Keep per-machine
    #    budget modest: enumerate rows up to 3 states per side first.
    for nl in range(1, 4):
        for nr in range(1, 4):
            # build row candidates with -1 allowed
            def rows(n):
                out = []
                # row: tuple over symbols of target in range(n) or -1
                def rec(k, acc):
                    if k == n_symbols:
                        out.append(tuple(acc))
                        return
                    for v in range(-1, n):
                        acc.append(v)
                        rec(k + 1, acc)
                        acc.pop()
                rec(0, [])
                return out
            RL = rows(nl)
            RR = rows(nr)
            # small optimization: only allow size-1 automata with loop
            for L in _product(RL, nl):
                if L[0][0] != 0:
                    continue
                for R in _product(RR, nr):
                    if R[0][0] != 0:
                        continue
                    cert = build_cps(table, n_states, n_symbols, L, R)
                    if cert is not None:
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None


def _product(seq, k):
    if k == 0:
        yield ()
        return
    for head in seq:
        for tail in _product(seq, k - 1):
            yield (head,) + tail