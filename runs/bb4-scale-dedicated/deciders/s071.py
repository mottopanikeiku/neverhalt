import sys
from collections import deque

STATE_A = 0

# machine table lookup helpers -------------------------------------------------

def _tab(tm):
    # returns dict: (state, symbol) -> (write, move, next) or None (halt)
    out = {}
    n = 0
    for row in tm.split("_"):
        if row == "---":
            continue
        for k in range(0, len(row), 3):
            chunk = row[k:k+3]
            if len(chunk) < 3 or chunk == "---":
                continue
            w, mv, nx = chunk
            if nx == "-":
                continue
            st = int(nx, 36) if nx.isdigit() else ord(nx) - ord("A")
            if st > n:
                n = st + 1
            out[(n - 1, int(w))] = (int(w), 1 if mv == "R" else -1, st)
    return out, n


def _sym(w):
    return int(w)


def _mk(tm):
    # machine table as dict (state, symbol) -> (write, move, next) or None
    rows = tm.split("_")
    table = {}
    order = {}
    for si, row in enumerate(rows):
        for k in range(0, len(row), 3):
            chunk = row[k:k+3]
            if len(chunk) < 3 or chunk == "---" or chunk[2] == "-":
                continue
            w, mv, nx = chunk
            ns = ord(nx) - ord("A") if nx.isalpha() else int(nx)
            table[(si, int(w))] = (int(w), 1 if mv == "R" else -1, ns)
            order[ns] = si + 1
    return table


def _contexts(tm):
    # all (state, symbol) transitions present
    tab = _mk(tm)
    ns = 0
    for (s, _x), (_w, _m, nx) in tab.items():
        ns = max(ns, nx + 1)
    return tab, ns


# BFS closure of contexts ------------------------------------------------------

def _closure(tm, left, right, max_ctx=200000):
    tab, ns = _contexts(tm)
    # context [l, q, s, r]
    start = (0, 0, 0, 0)
    seen = {start}
    dq = deque([start])
    while dq:
        l, q, s, r = dq.popleft()
        tr = tab.get((q, s))
        if tr is None:
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                row = right[r2]
                for s2 in (0, 1):
                    if row[s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            dq.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                row = left[l2]
                for s2 in (0, 1):
                    if row[s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            dq.append(ctx)
        if len(seen) > max_ctx:
            return None
    if len(seen) > 200000:
        return None
    # emit
    L = [[left[i][0], left[i][1]] for i in range(len(left))]
    R = [[right[i][0], right[i][1]] for i in range(len(right))]
    ctxs = [[c[0], c[1], c[2], c[3]] for c in seen]
    # verify start context present (it is) and no halting context (closure returned None if any)
    return {"kind": "cps", "left": L, "right": R, "contexts": ctxs}


# DFA enumeration --------------------------------------------------------------

def _enumerate_tables(nstates):
    # state 0 loops on symbol 0 and is absorbing on 0; that is, left[0][0] == 0.
    # enumerate all deterministic tables for states 0..nstates-1 with left[0][0] == 0.
    # represent as tuple of 2*nstates entries in {0..nstates-1, None}
    idx = list(range(nstates))
    choices = idx + [None]
    # we need left[0][0] == 0 fixed
    total = len(choices) ** (2 * nstates - 1)
    if total > 3_000_000:
        return
    from itertools import product
    for combo in product(choices, repeat=2 * nstates - 1):
        tab = [None] * (2 * nstates)
        tab[0] = 0
        for i, v in enumerate(combo):
            tab[2 * i + 1 + (0 if i < nstates - 1 else 0)] = v
        # rebuild properly
        t = [None] * (2 * nstates)
        t[0] = 0
        j = 0
        for si in range(nstates):
            for sym in (0, 1):
                pos = 2 * si + sym
                if pos == 0:
                    continue
                t[pos] = combo[j]
                j += 1
        yield t


def _dfa_from_table(t, n):
    return [[t[2 * i], t[2 * i + 1]] for i in range(n)]


def decide(tm: str):
    tab, ns = _contexts(tm)
    # the blank tape is state 0 of each automaton: left[0][0] == right[0][0] == 0
    # try left tables with 1..3 states; right table = same enumeration, but
    # keep right[0][0] == 0 too.
    nmax = 3
    for nl in (1, 2, 3):
        for nt in _enumerate_tables(nl):
            left = _dfa_from_table(nt, nl)
            # left[0][0] must be 0 (guaranteed); also left[0][1] may be anything
            for nr in (1, 2, 3):
                for rt in _enumerate_tables(nr):
                    right = _dfa_from_table(rt, nr)
                    cert = _closure(tm, left, right)
                    if cert is not None:
                        # kernel may still reject; caller will check
                        return cert
    return None
