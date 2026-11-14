import sys
from collections import deque
from neverhalt.tm import parse, run

def trans(tm):
    tab, ns, sy = parse(tm)
    return tab, ns, sy

def mk_left(n):
    # n-gram remembering last n cells of the left half-tape, read far->head.
    # state encodes the n-gram value seen so far, canonical BFS order.
    n = max(1, n)
    states = 2 ** n
    tab = [[0] * 2 for _ in range(states)]
    for s in range(states):
        for x in (0, 1):
            tab[s][x] = ((s << 1) | x) & (states - 1)
    return tab

def mk_right(n):
    return mk_left(n)

def closure(tab, ns, sy, left, right):
    # left[i][x]: int or None ; right likewise
    # context (l, q, s, r) closed under the step rules.
    start = (0, 0, 0, 0)
    seen = set([start])
    dq = deque([start])
    ctx = set([start])
    while dq:
        l, q, s, r = dq.popleft()
        if q not in range(ns) or s not in range(sy):
            continue
        if (q, s) not in tab:
            return None  # halting context
        w, mv, q2 = tab[(q, s)]
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(sy):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
                            ctx.add(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(sy):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            dq.append(c)
                            ctx.add(c)
    return ctx

def emit(tab, ns, sy, left, right, ctx):
    L = [[left[i][0], left[i][1]] for i in range(len(left))]
    R = [[right[i][0], right[i][1]] for i in range(len(right))]
    C = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": L, "right": R, "contexts": C}

def try_cps(tm):
    tab, ns, sy = trans(tm)
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            try:
                left = mk_left(nl)
                right = mk_right(nr)
            except Exception:
                continue
            ctx = closure(tab, ns, sy, left, right)
            if ctx is not None:
                return emit(tab, ns, sy, left, right, ctx)
    return None

def decide(tm):
    try:
        return try_cps(tm)
    except Exception:
        return None

if __name__ == "__main__":
    pass
