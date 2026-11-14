import sys
from collections import deque
from neverhalt.tm import parse, run

# ---- machine table helpers -------------------------------------------------
def mtable(tm):
    t, ns, sy = parse(tm)
    M = {}
    for q in range(ns):
        for s in range(sy):
            if (q, s) in t:
                w, mv, q2 = t[(q, s)]
                M[(q, s)] = (w, mv, q2)
    return M, ns, sy

def halt_ctx(M, ns, sy, q, s):
    return (q, s) not in M

# ---- backward reachability to a halt --------------------------------------
def backward_halt(M, ns, sy):
    # B[q] = set of symbols s such that from (q,s) some halting transition is
    # reachable.  Computed by iterating the transition relation.
    B = {q: set() for q in range(ns)}
    changed = True
    while changed:
        changed = False
        for q in range(ns):
            for s in range(sy):
                if s in B[q]:
                    continue
                tr = M.get((q, s))
                if tr is None:
                    B[q].add(s)
                    changed = True
                    continue
                w, mv, q2 = tr
                # after writing w and moving, the head reads the next cell
                if w in B.get(q2, ()):
                    B[q].add(s)
                    changed = True
    return B

def reaches_halt(M, ns, sy, q, s, B):
    # explicit DFS over (state, symbol) pairs
    seen = set()
    st = [(q, s)]
    while st:
        a, b = st.pop()
        if (a, b) in seen:
            continue
        seen.add((a, b))
        tr = M.get((a, b))
        if tr is None:
            return True
        w, mv, q2 = tr
        if w in B.get(q2, ()):
            return True
        if (q2, b) not in seen:
            st.append((q2, b))
    return False

# ---- DFA enumeration (BFS-open, canonical by reachable state count) -------
def canon(states, delta):
    # states: list of ints (0..n-1).  BFS from 0 on symbol 0 first.
    if not states:
        return None
    idx = {s: i for i, s in enumerate(states)}
    start = idx[0]
    order = []
    seen = {start}
    dq = deque([start])
    while dq:
        u = dq.popleft()
        order.append(u)
        for x in range(2):
            v = delta[u][x]
            if v is not None and v not in seen:
                seen.add(v)
                dq.append(v)
    if len(order) != len(states):
        return None
    remap = {old: new for new, old in enumerate(order)}
    nd = len(order)
    ndelta = [[None, None] for _ in range(nd)]
    for u in range(nd):
        for x in range(2):
            v = delta[order[u]][x]
            if v is not None:
                ndelta[u][x] = remap[v]
    return nd, ndelta

def enumerate_dfa(max_states, B, ns, sy, budget):
    # yields (n, delta) canonical DFAs, n from 1..max_states.
    # delta[u][x] = v or None.  State 0 loops on 0.
    # Partial tables are pruned when a symbol forces a halt-reachable tape.
    out = []
    # level-by-level: represent partial table as list of rows, each row a
    # tuple (d0, d1) with None meaning "unassigned".
    frontier = [((0, 0),)]  # row 0: on 0 stay 0
    for n in range(1, max_states + 1):
        if budget[0] <= 0:
            break
        newf = []
        for table in frontier:
            budget[0] -= 1
            if budget[0] <= 0:
                break
            # complete the table by assigning unassigned entries
            rows = [list(r) for r in table]
            assign = []
            for i in range(n):
                for x in range(2):
                    if rows[i][x] is None:
                        assign.append((i, x))
            # enumerate assignments lazily; prune via halt-reachability
            def rec(k, rows, assign):
                nonlocal budget
                if budget[0] <= 0:
                    return
                if k == len(assign):
                    # canonicalize and check state 0 loops on 0
                    got = canon(list(range(n)), rows)
                    if got is None:
                        return
                    nn, nd = got
                    out.append((nn, nd))
                    return
                i, x = assign[k]
                for v in range(n):
                    rows[i][x] = v
                    # prune: if this assignment makes (q, s) with s==x reachable
                    # on a tape that can halt, drop it.  We approximate by
                    # checking whether the tape represented by state i can
                    # still reach a halt: for DFA purposes, the tape's last
                    # symbol is x, so a machine state q reading x would halt
                    # if the tape continues as blank.  We keep it simple:
                    # only prune when the written symbol leads to a halt.
                    # (the caller's context closure does the real work)
                    rec(k + 1, rows, assign)
                    rows[i][x] = None
            rec(0, rows, assign)
        frontier = newf
    return out

# ---- context closure ------------------------------------------------------
def closure(M, ns, sy, D):
    # D: list of (n, delta).  Build the product automaton on (l, r) and run the
    # context fixpoint.  Returns a certificate dict or None.
    # We try all pairs of DFAs.
    for (nl, dl) in D:
        for (nr, dr) in D:
            ctx = set()
            if (0, 0, 0, 0) not in ctx:
                ctx.add((0, 0, 0, 0))
            work = deque([(0, 0, 0, 0)])
            ok = True
            while work:
                l, q, s, r = work.popleft()
                tr = M.get((q, s))
                if tr is None:
                    ok = False
                    break
                w, mv, q2 = tr
                if mv > 0:
                    l2 = dl[l][w]
                    if l2 is None:
                        ok = False
                        break
                    # for every (r2, s2) with dr[r2][s2] == r
                    for r2 in range(nr):
                        for s2 in range(sy):
                            if dr[r2][s2] == r:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    ctx.add(c)
                                    work.append(c)
                else:
                    r2 = dr[r][w]
                    if r2 is None:
                        ok = False
                        break
                    for l2 in range(nl):
                        for s2 in range(sy):
                            if dl[l2][s2] == l:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    ctx.add(c)
                                    work.append(c)
            if not ok:
                continue
            if len(ctx) > 200000:
                continue
            left = [[dl[i][x] for x in range(sy)] for i in range(nl)]
            right = [[dr[i][x] for x in range(sy)] for i in range(nr)]
            contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
            return {"kind": "cps", "left": left, "right": right,
                    "contexts": contexts}
    return None

# ---- main -----------------------------------------------------------------
def decide(tm):
    try:
        M, ns, sy = mtable(tm)
    except Exception:
        return None
    # quick: if the machine halts, nothing to prove
    h, steps, st, pos, tape = run(tm, 20000)
    if h:
        return None
    B = backward_halt(M, ns, sy)
    # budget for DFA enumeration
    budget = [400000]
    D = enumerate_dfa(3, B, ns, sy, budget)
    cert = closure(M, ns, sy, D)
    if cert is not None:
        from neverhalt.kernel import check
        try:
            check(tm, cert)
            return cert
        except Exception:
            return None
    return None


DECIDER_NAME = "dfa-cps-search"

if __name__ == "__main__":
    import json
    tm = sys.argv[1]
    c = decide(tm)
    print(json.dumps(c) if c else "None")
