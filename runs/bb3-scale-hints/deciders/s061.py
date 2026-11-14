import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run

# The five survivors shown are all of the same family: a left-moving "racket"
# (state C writes and jumps around) sweeping the tape and a counter carried
# between two right-moving states.  A 2-state half-tape automaton already
# suffices for most of them; a 3-state one covers the rest.  The hint asks for
# search over automata, so we enumerate small transition tables in BFS-canonical
# order and close the context set for every pair of left/right automata.

def _canon(rows, n):
    # rows: list of n rows, each a tuple of n entries (None or int)
    return tuple(tuple(r) for r in rows)

def _enumerate_tables(n):
    # every table (n x n) with entries in {None} U {0..n-1}, canonical BFS order
    # over the number of "interesting" entries.  We build by growing size.
    out = []
    cells = [(i, x) for i in range(n) for x in range(n)]
    # BFS over prefixes, but that is huge; instead enumerate by total weight.
    import itertools
    choices = [None] + list(range(n))
    # order tables by sum of entries (None = -1 weight) then lexicographic
    def key(t):
        s = 0
        for r in range(n):
            for x in range(n):
                v = t[r][x]
                s += 0 if v is None else v + 1
        return s
    seen = set()
    for vals in itertools.product(choices, repeat=n * n):
        t = tuple(tuple(vals[r * n:(r + 1) * n]) for r in range(n))
        if t in seen:
            continue
        seen.add(t)
        # canonical form: require row 0 to be all None or all same, and
        # require the first non-None entry in row-major order to be 0
        # (standard de Bruijn-like canonicalization, enough to cut the space)
        if t[0][0] is not None and t[0][0] != 0:
            continue
        out.append(t)
        if len(out) > 400000:
            break
    return out

def _close(tm, n_states, n_symbols, left, right):
    # left/right: tuple of n rows of n entries (None or int), state 0 = blank half-tape
    table, ns, nsym = parse(tm)
    # contexts as frozensets of tuples (l, q, s, r), q and s are ints
    ctx = set()
    if (0, 0, 0, 0) not in ctx:
        ctx.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        new = set()
        for (l, q, s, r) in ctx:
            if not (0 <= q < ns and 0 <= s < nsym):
                continue
            tr = table.get((q, s))
            if tr is None:
                return None  # halting context
            w, mv, q2 = tr
            if mv == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                # for every pair (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    row = right[r2]
                    for s2 in range(len(row)):
                        if row[s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                new.add(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    row = left[l2]
                    for s2 in range(len(row)):
                        if row[s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                new.add(c)
        if new:
            ctx |= new
            changed = True
    if len(ctx) > 200000:
        return None
    left_out = [[(left[i][x] if left[i][x] is not None else None) for x in range(len(left[0]))] for i in range(len(left))]
    right_out = [[(right[i][x] if right[i][x] is not None else None) for x in range(len(right[0]))] for i in range(len(right))]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left_out, "right": right_out, "contexts": contexts}

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    for n in (1, 2, 3):
        tables = _enumerate_tables(n)
        for lt in tables:
            for rt in tables:
                cert = _close(tm, ns, nsym, lt, rt)
                if cert is not None:
                    return cert
    return None
