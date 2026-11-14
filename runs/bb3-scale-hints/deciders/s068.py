from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

HALT = -1

# ---------- helpers ----------
from collections import deque


def _state_table(table, n_states, sym):
    # return dict[(state,sym)] -> (write,move,next) or None
    return table


def _tick(tm):
    t, ns, sy = parse(tm)
    return t, ns, sy


# ---------- C1: enumerate tiny automata, ngram-style, 1..3 states ----------
# automaton state 0 = all-blank, loops on symbol 0.
def _build_side(n, alphabet, keep_loop0=True):
    """enumerate deterministic automata on n states over alphabet [0,1].
    State 0 loops on 0. All other transitions arbitrary."""
    out = []
    # transitions: for each state 1..n-1, for each symbol, target in 0..n-1
    states = list(range(n))
    # total combos = n^(2*(n-1))
    import itertools
    slots = [(s, x) for s in states[1:] for x in range(2)]
    if keep_loop0:
        slots = [sl for sl in slots if not (sl[0] == 0)]
    # for state 0, both symbols loop to 0
    for vals in itertools.product(states, repeat=len(slots)):
        tab = [[0, 0] for _ in range(n)]
        for (s, x), v in zip(slots, vals):
            tab[s][x] = v
        out.append(tab)
    return out


def _closure(tm, t, ns, sy):
    """Closed-context fixpoint. Returns list of contexts [l,q,s,r] or None."""
    # transitions
    trans = {}
    for q in range(ns):
        for s in range(sy):
            tr = t.get((q, s))
            if tr is None:
                return None  # halting context exists
            trans[(q, s)] = tr
    # context: (l, q, s, r)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        (l, q, s, r) = frontier.popleft()
        (w, mv, q2) = trans[(q, s)]
        if mv == +1:
            # left pushes w: l2 = L[l][w]; right pops s2 with R[r2][s2]==r
            l2 = None
            if l is not None:
                l2 = None
            # we need automata; we'll pass them separately -- handled outside
            raise RuntimeError
    return None


def _run_closure(tm, t, ns, sy, L, R):
    trans = {}
    for q in range(ns):
        for s in range(sy):
            tr = t.get((q, s))
            if tr is None:
                return None
            trans[(q, s)] = tr
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        (l, q, s, r) = frontier.popleft()
        (w, mv, q2) = trans[(q, s)]
        if mv == +1:
            if L[l][w] is None:
                return None
            l2 = L[l][w]
            # for every (r2, s2) with R[r2][s2] == r:
            for r2 in range(len(R)):
                for s2 in range(len(R[0])):
                    if R[r2][s2] == r:
                        nc = (l2, q2, s2, r2)
                        if nc not in ctx:
                            ctx.add(nc)
                            frontier.append(nc)
        else:
            if R[r][w] is None:
                return None
            r2 = R[r][w]
            for l2 in range(len(L)):
                for s2 in range(len(L[0])):
                    if L[l2][s2] == l:
                        nc = (l2, q2, s2, r2)
                        if nc not in ctx:
                            ctx.add(nc)
                            frontier.append(nc)
    # build certificate
    if len(ctx) > 200000:
        return None
    left = [list(row) for row in L]
    right = [list(row) for row in R]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left, "right": right, "contexts": contexts}


# ---------- C2: ngram automata ----------
def _ngram_side(width, alphabet_size=2):
    """return transition table for n-gram automaton of given width, remembering last `width` cells."""
    n = 2 ** width
    tab = [[0] * alphabet_size for _ in range(n)]
    for st in range(n):
        for x in range(alphabet_size):
            # shift left, append x
            tab[st][x] = ((st << 1) | x) & (n - 1)
    return tab


def _try_ngram(tm):
    t, ns, sy = parse(tm)
    for w in (0, 1, 2, 3, 4, 5, 6):
        if w == 0:
            L = [[0]]
            R = [[0]]
        else:
            L = _ngram_side(w, sy)
            R = _ngram_side(w, sy)
        if len(R) > 5000:
            break
        cert = _run_closure(tm, t, ns, sy, L, R)
        if cert is not None:
            try:
                return check(tm, cert)
            except Reject:
                continue
    return None


# ---------- C3: enumerate small automata pairs, 1..3 states per side ----------
def _enumerate_pairs(tm):
    t, ns, sy = parse(tm)
    if ns > 3:
        return None
    # try widths 1..3 states
    for n in (1, 2, 3):
        if 2 ** n > 0 and (n - 1) * 2 * 2 ** (2 * (n - 1)) > 400000:
            break
        Ls = _build_side(n, sy)
        Rs = _build_side(n, sy)
        for L in Ls:
            for R in Rs:
                cert = _run_closure(tm, t, ns, sy, L, R)
                if cert is not None and len(cert["contexts"]) <= 200000:
                    try:
                        r = check(tm, cert)
                        if r is not None:
                            return cert
                    except Reject:
                        pass
        if n == 2 and len(Ls) * len(Rs) > 3000:
            break
    return None


def decide(tm: str) -> dict | None:
    # cheap: try ngram widths
    try:
        c = _try_ngram(tm)
        if c is not None:
            return c
    except Exception:
        pass
    # then enumerate tiny automata
    try:
        c = _enumerate_pairs(tm)
        if c is not None:
            return c
    except Exception:
        pass
    return None
