import sys
from neverhalt.tm import parse

def build_auto(n, alphabet=2):
    # enumerate deterministic partial automata, state 0 loops on 0
    out = []
    def rec(rows, states):
        if states == n:
            out.append([row[:] for row in rows])
            return True
        row = []
        for x in range(alphabet):
            if x == 0 and states == 0:
                row.append(0)
            else:
                row.append(-1)
        # fill remaining entries with either -1 or any existing state
        def go(i, used):
            if i == len(row):
                if used:
                    out.append([r[:] for r in rows] + [row])
                return
            if used or (x == 0 and states == 0):
                go(i+1, used)
                return
            # try -1 first
            row[i] = -1
            go(i+1, used)
            # try each existing state
            for s in range(states):
                row[i] = s
                go(i+1, True)
            row[i] = -1
        go(0, False)
        return False
    rec([], 0)
    return out

def tr_auto(a, s, x):
    if 0 <= s < len(a):
        return a[s][x]
    return -1

def step_auto(a, s, x):
    n = tr_auto(a, s, x)
    if n < 0:
        return None
    return n

def close_contexts(tm, left, right, limit=200000):
    table, nstates, nsym = parse(tm)
    states = range(nstates)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier and len(ctx) < limit:
        nxt = []
        for (l, q, s, r) in frontier:
            if s >= nsym:
                continue
            key = (q, s)
            if key not in table:
                continue
            w, mv, q2 = table[key]
            if mv == 1:
                l2 = step_auto(left, l, w)
                if l2 is None:
                    continue
                for (r2, s2) in right_pairs(right, r):
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        nxt.append(c)
            else:
                r2 = step_auto(right, r, w)
                if r2 is None:
                    continue
                for (l2, s2) in left_pairs(left, l):
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        nxt.append(c)
        frontier = nxt
    return ctx

def right_pairs(a, r):
    out = []
    for s in range(len(a[0]) if a else 0):
        if 0 <= r < len(a):
            n = a[r][s]
            if n >= 0:
                out.append((n, s))
    return out

def left_pairs(a, l):
    out = []
    for s in range(len(a[0]) if a else 0):
        if 0 <= l < len(a):
            n = a[l][s]
            if n >= 0:
                out.append((n, s))
    return out

def has_halt(tm, ctx):
    table, nstates, nsym = parse(tm)
    for (l, q, s, r) in ctx:
        if (q, s) not in table:
            return True
    return False

def emit(tm, left, right, ctx):
    L = [[None]*2 for _ in range(len(left))]
    for i, row in enumerate(left):
        for x, v in enumerate(row):
            if v >= 0:
                L[i][x] = v
    R = [[None]*2 for _ in range(len(right))]
    for i, row in enumerate(right):
        for x, v in enumerate(row):
            if v >= 0:
                R[i][x] = v
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": L, "right": R, "contexts": contexts}

def decide(tm):
    table, nstates, nsym = parse(tm)
    # quick check: no halting context possible if state 0 blank loops
    # enumerate left automata up to 3 states, right automata up to 3 states
    autos = []
    for n in (1, 2, 3):
        autos.extend(build_auto(n))
        if len(autos) > 400:
            break
    for left in autos:
        for right in autos:
            ctx = close_contexts(tm, left, right, limit=200000)
            if len(ctx) > 200000:
                continue
            if not has_halt(tm, ctx):
                return emit(tm, left, right, ctx)
    return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    if c:
        print("FOUND")
    else:
        print("NONE")
