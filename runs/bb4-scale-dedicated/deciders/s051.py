import sys
from neverhalt.tm import parse

sys.setrecursionlimit(100000)


def _canonical(dfa):
    n = len(dfa)
    seen = {}
    order = []

    def visit(i):
        if i in seen:
            return
        seen[i] = len(order)
        order.append(i)
        for x in (0, 1):
            j = dfa[i][x]
            if j is not None:
                visit(j)

    visit(0)
    remap = {i: seen[i] for i in seen}
    out = []
    for i in sorted(remap.values()):
        src = [j for j, v in remap.items() if v == i][0]
        row = [remap[dfa[src][x]] if dfa[src][x] is not None else None for x in (0, 1)]
        out.append(row)
    return out


def _closure(table, n_states, n_symb, left, right):
    ctx = {}
    stack = [(0, 0, 0, 0)]
    ctx[(0, 0, 0, 0)] = True
    while stack:
        l, q, s, r = stack.pop()
        if (q, s) not in table:
            return None
        w, move, q2 = table[(q, s)]
        if move == 1:
            l2 = left[l][w] if w < len(left) and l < len(left) else None
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        k = (l2, q2, s2, r2)
                        if k not in ctx:
                            ctx[k] = True
                            stack.append(k)
        else:
            r2 = right[r][w] if w < len(right) and r < len(right) else None
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        k = (l2, q2, s2, r2)
                        if k not in ctx:
                            ctx[k] = True
                            stack.append(k)
    return ctx


def decide(tm):
    try:
        table, n_states, n_symb = parse(tm)
    except Exception:
        return None
    if n_symb != 2:
        return None
    n = n_states
    if n > 4:
        return None
    # enumerate left DFAs in BFS-canonical order, 1..6 states
    candidates = []
    seen = set()
    frontier = [([None, None],)]
    for size in range(1, 7):
        nxt = []
        for dfa in frontier:
            c = _canonical(dfa)
            key = tuple(tuple(x) for x in c)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(c)
            for i in range(size):
                for x in (0, 1):
                    for j in range(size + 1):
                        nd = [row[:] for row in dfa]
                        nd[i][x] = j
                        nxt.append(nd)
        frontier = nxt
        if len(candidates) > 40000:
            break
    for left in candidates:
        if left[0][0] != 0 or left[0][0] != 0:
            continue
        if left[0][0] != 0:
            continue
        # right: mirror of left by reversing cell order is not enough; use left itself
        right = left
        ctx = _closure(table, n, n_symb, left, right)
        if ctx is None:
            continue
        if len(ctx) > 200000:
            continue
        contexts = [[list(k) for k in ctx]]
        cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts[0]}
        return cert
    return None
