from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: CPS with half-tape automata found by search (1..N states per side,
# state 0 loops on 0 so the blank half-tape stays in state 0).
# For each pair we close contexts to a fixed point, and keep only the used
# transitions (null elsewhere).  First pair whose closure is halting-free
# wins.  Automata up to AUT_MAX states per side; contexts capped for safety.

AUT_MAX = 3          # states per side (0..AUT_MAX-1); grow if time allows
CTX_CAP = 200000

def _automata(size):
    # yield all deterministic tables with 'size' states, index 0 = blank loop.
    # table[i][x] in {1..size} or None (x = 0 or 1).
    import itertools
    rng = range(1, size + 1)
    for vals in itertools.product(rng + (None,), repeat=2 * (size - 1)):
        t = [[0, 0]]
        ok = True
        for i in range(1, size):
            t.append([vals[2 * (i - 1)], vals[2 * (i - 1) + 1]])
        yield t

def _close_contexts(tm, tab, left, right):
    """Fixed point of contexts [l,q,s,r]; returns set or None if too big."""
    n_states, n_syms = tab[1], tab[2]
    # map halting: transitions absent from table
    ctx = {(0, 0, 0, 0)}
    frontier = [(0, 0, 0, 0)]
    while frontier:
        newf = []
        for (l, q, s, r) in frontier:
            if q >= n_states:
                continue
            key = (q, s)
            if key not in tab[0]:
                return None  # halting context -> reject this pair
            w, move, q2 = tab[0][key]
            if move == +1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                newf.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                newf.append(c)
            if len(ctx) > CTX_CAP:
                return None
        frontier = newf
    return ctx

def decide(tm: str):
    tab, n_states, n_syms = parse(tm)
    # quick sanity: blank tape start 0
    for ls in range(1, AUT_MAX + 1):
        for rs in range(1, AUT_MAX + 1):
            for left in _automata(ls):
                for right in _automata(rs):
                    ctx = _close_contexts(tm, tab, left, right)
                    if ctx is None:
                        continue
                    # build certificate
                    left_tab = [[left[i][0], left[i][1]] for i in range(ls)]
                    right_tab = [[right[i][0], right[i][1]] for i in range(rs)]
                    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                    cert = {
                        "kind": "cps",
                        "left": left_tab,
                        "right": right_tab,
                        "contexts": contexts,
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None
