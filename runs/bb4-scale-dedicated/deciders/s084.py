import sys
from collections import deque

sys.setrecursionlimit(10000)


def _symbols(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _build_left_automata(n_states):
    # Enumerate DFA transition tables left[i][x], i in 0..n-1, x in 0..1,
    # with left[0][0] == 0 (blank half-tape loops on blank).  The automaton
    # reads cells far away towards the head, so we enumerate reachable tables.
    out = []
    k = n_states
    for bits in range((k * k) ** 2):
        t = bits
        tab = [[0, 0] for _ in range(k)]
        ok = True
        for i in range(k):
            for x in (0, 1):
                tab[i][x] = t % k
                t //= k
        if tab[0][0] != 0:
            continue
        out.append(tab)
    return out


def _build_right_automata(n_states):
    # Same enumeration; right[0][0] == 0 is required by the kernel.
    return _build_left_automata(n_states)


def _pair_closure(table, n_states, n_symbols, left, right):
    # Contexts: (l, q, s, r).  l indexes the left automaton, r the right one.
    # State 0 of each automaton is the all-blank half-tape.
    nL = len(left)
    nR = len(right)
    start = (0, 0, 0, 0)
    seen = {start}
    q = deque([start])
    halt = False
    while q:
        (l, st, sy, r) = q.popleft()
        key = (st, sy)
        tr = table.get(key)
        if tr is None:
            return None
        w, mv, st2 = tr
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for (r2, s2) in _right_targets(right, r):
                ctx = (l2, st2, s2, r2)
                if ctx not in seen:
                    seen.add(ctx)
                    q.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for (l2, s2) in _left_targets(left, l):
                ctx = (l2, st2, s2, r2)
                if ctx not in seen:
                    seen.add(ctx)
                    q.append(ctx)
    return seen


def _right_targets(right, r):
    res = []
    for s2 in (0, 1):
        r2 = right[r][s2]
        if r2 is not None:
            res.append((r2, s2))
    return res


def _left_targets(left, l):
    res = []
    for s2 in (0, 1):
        l2 = left[l][s2]
        if l2 is not None:
            res.append((l2, s2))
    return res


def decide(tm):
    table, n_states, n_symbols = _symbols(tm)
    # Normalize: states are ints, A = 0, symbols 0 and 1.
    for nL in (1, 2, 3, 4):
        lefts = _build_left_automata(nL)
        for nR in (1, 2, 3, 4):
            rights = _build_right_automata(nR)
            for left in lefts:
                for right in rights:
                    if right[0][0] != 0:
                        continue
                    ctx = _pair_closure(table, n_states, n_symbols, left, right)
                    if ctx is None:
                        continue
                    # Emit certificate, dropping unused transitions.
                    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                    cert = {
                        "kind": "cps",
                        "left": [[left[i][0], left[i][1]] for i in range(nL)],
                        "right": [[right[i][0], right[i][1]] for i in range(nR)],
                        "contexts": contexts,
                    }
                    try:
                        from neverhalt.kernel import check
                        check(tm, cert)
                        return cert
                    except Exception:
                        continue
    return None


def parse(tm):
    from neverhalt.tm import parse as _p
    return _p(tm)


def run(tm, max_steps):
    from neverhalt.tm import run as _r
    return _r(tm, max_steps)