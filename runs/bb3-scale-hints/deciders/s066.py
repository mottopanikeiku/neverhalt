import sys
from collections import defaultdict, deque
from neverhalt.tm import parse, run

sys.setrecursionlimit(100000)

# ---------------------------------------------------------------
# helpers
# ---------------------------------------------------------------

def mtable(tm):
    t, ns, nsym = parse(tm)
    return {(st, sym): tr for (st, sym), tr in t.items()}

def step(tm, state, tape, pos):
    t, ns, nsym = parse(tm)
    tr = t.get((state, tape.get(pos, 0)))
    if tr is None:
        return None
    w, mv, nxt = tr
    tape[pos] = w
    return nxt, pos + mv

def run_steps(tm, n):
    t, ns, nsym = parse(tm)
    tape = {}
    st, pos = 0, 0
    for _ in range(n):
        tr = t.get((st, tape.get(pos, 0)))
        if tr is None:
            return (False, pos, tape)
        w, mv, nxt = tr
        tape[pos] = w
        st, pos = nxt, pos + mv
    return (True, pos, tape)

# ---------------------------------------------------------------
# certificate emitters
# ---------------------------------------------------------------

def emit_cycle(tm, T, P, d, lo, hi, kind="cycle"):
    # sanity-check before returning
    run_steps(tm, T)
    tape1 = {}
    from neverhalt.tm import run as _run
    _run(tm, T)
    return {"kind": kind, "t": T, "p": P}

def emit_cps(tm, left, right, contexts):
    # contexts: list of (l, q, s, r)
    return {"kind": "cps", "left": left, "right": right,
            "contexts": [[l, q, s, r] for (l, q, s, r) in contexts]}

# ---------------------------------------------------------------
# CPS closure
# ---------------------------------------------------------------

def closure(tm, left, right):
    """Closed context set for given automata. Returns (ctxs, ok)."""
    mtab = mtable(tm)
    states = range(1, 1 + max(len(left), len(right)))
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [ctx.pop()]
    while frontier:
        l, q, s, r = frontier.pop()
        tr = mtab.get((q, s))
        if tr is None:
            return None, False
        w, mv, q2 = tr
        if mv == 1:  # right move
            l2 = left[l][w]
            if l2 is None:
                return None, False
            for (r2, s2) in right_pairs(right, r):
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    ctx.add(c)
                    frontier.append(c)
        else:  # left move
            r2 = right[r][w]
            if r2 is None:
                return None, False
            for (l2, s2) in left_pairs(left, l):
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    ctx.add(c)
                    frontier.append(c)
    return ctx, True

def left_pairs(left, l):
    res = []
    for i in range(len(left)):
        for x in (0, 1):
            if left[i][x] == l:
                res.append((i, x))
    return res

def right_pairs(right, r):
    res = []
    for i in range(len(right)):
        for x in (0, 1):
            if right[i][x] == r:
                res.append((i, x))
    return res

# ---------------------------------------------------------------
# DFA enumeration
# ---------------------------------------------------------------

def make_automaton(size):
    """Automaton: state 0 = all blank. left[0][0] == 0."""
    # rows 0..size-1, columns 0,1
    return [[0 if (i in (0, size - 1) or (i, 0) == (0 if False else -1, 0)) else 0 for _ in range(2)] for i in range(size)]

def enumerate_automata(maxsize):
    """BFS-canonical enumeration of DFAs up to maxsize states.
    State 0 loops on 0 and is the all-blank sink on 0."""
    for size in range(1, maxsize + 1):
        yield from enumerate_size(size)

def enumerate_size(size):
    # rows: states 0..size-1, transitions 0/1 -> state or -1 (null)
    alphabet = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    alphabet = [x for x in alphabet if x < size] + [-1]
    for t0 in alphabet:
        for t1 in alphabet:
            if size == 1:
                # only automaton: state 0 -> 0 on 0
                if t0 == 0 and t1 in (-1, 0):
                    yield [[0, t1]]
            else:
                # state 0 must loop on 0 (blank half-tape reads blank stays blank)
                if t0 != 0:
                    continue
                yield from _enum_rows(size, 1, t0, t1)

def _enum_rows(size, rowidx, a00, a01):
    if rowidx == size:
        yield [[a00, a01]]
        return
    opts = list(range(size)) + [-1]
    for t0 in opts:
        for t1 in opts:
            yield from _enum_rows(size, rowidx + 1, t0, t1)

# Better: build incrementally with backtracking
def gen_automata(size):
    rows = [[0, 0] for _ in range(size)]
    rows[0][0] = 0
    def rec(i, j, blanks):
        if i == size and j == 0:
            # canonical: skip if identical automaton already produced
            yield [list(r) for r in rows]
            return
        if i == size:
            yield from rec(0, 0, blanks)
            return
        opts = list(range(size)) + [-1]
        for v in opts:
            if i == 0 and j == 0:
                if v != 0:
                    continue
            rows[i][j] = v
            if j == 1:
                yield from rec(i + 1, 0, blanks)
            else:
                yield from rec(i, 1, blanks)
            rows[i][j] = 0
    seen = set()
    for a in rec(0, 0, 0):
        key = tuple(tuple(r) for r in a)
        if key in seen:
            continue
        seen.add(key)
        yield a

def ngram_automaton(n):
    """Remember last n cells; state = tuple of last n symbols."""
    # map tuples -> ints, state 0 = all blank
    nums = [(0,) * n]
    idx = {(0,) * n: 0}
    num = 1
    rows = [[0, 0]]
    rows[0][0] = 0
    # rows for each state: on symbol x, append x, drop oldest
    for st in range(0, num):
        pass
    # build lazily
    states = 1
    rows = [[0, 0]]
    # state encoding: index in list
    enc = {(0,) * n: 0}
    order = [(0,) * n]
    k = 0
    while k < len(order):
        tup = order[k]
        for x in (0, 1):
            nt = (tup[1:] + (x,))
            if nt not in enc:
                enc[nt] = len(order)
                order.append(nt)
        k += 1
    size = len(order)
    # ensure at least 2 states
    if size < 2:
        size = 2
    rows = [[0, 0] for _ in range(size)]
    rows[0][0] = 0
    for tup, st in enc.items():
        if st >= size:
            continue
        for x in (0, 1):
            nt = (tup[1:] + (x,))
            rows[st][x] = enc.get(nt, st)
    if size <= 1:
        rows = [[0, 0]]
    return rows

# ---------------------------------------------------------------
# main decider
# ---------------------------------------------------------------

def decide(tm: str):
    # try n-gram automata for a range of n on both sides
    for n in range(1, 5):
        L = ngram_automaton(n)
        R = L
        ctx, ok = closure(tm, L, R)
        if ok and ctx:
            return emit_cps(tm, L, R, ctx)
    return None

DECIDER = decide