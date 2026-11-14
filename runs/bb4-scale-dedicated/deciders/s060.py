from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "small-cps-search"

def _trans_of(tm):
    table, n_states, n_symbols = parse(tm)
    tr = {}
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) in table:
                tr[(q, s)] = table[(q, s)]
    return tr, n_states, n_symbols

def _closure_for(tm, left, right, tr, ns, syms):
    # left[i][x]: state for reading x from far left toward head, or None
    # right[i][x]: same for right side
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = list(ctx)
    while frontier:
        l, q, s, r = frontier.pop()
        if (q, s) not in tr:
            return None
        w, mv, q2 = tr[(q, s)]
        if mv > 0:
            if w not in left[l]:
                return None
            l2 = left[l][w]
            for r2 in range(len(right)):
                for s2 in range(syms):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            if w not in right[r]:
                return None
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in range(syms):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
    return ctx

def _emit(tm, left, right, ctx):
    L = [[left[i][x] for x in range(2)] for i in range(len(left))]
    R = [[right[i][x] for x in range(2)] for i in range(len(right))]
    contexts = [[list(c) for c in ctx]]
    flat = []
    for c in ctx:
        flat.append([c[0], c[1], c[2], c[3]])
    cert = {"kind": "cps", "left": L, "right": R, "contexts": flat}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None

def _search_side(tm, side):
    # enumerate small left DFAs up to 3 states: state 0 loops on 0
    # each DFA row: [state_on_0, state_on_1]
    rows = []
    for s0 in range(3):
        for s1 in range(3):
            rows.append([s0, s1])
    # canonical BFS order: build tables of size n by assigning rows to states
    import itertools
    for n in range(1, 4):
        # state 0 must loop on 0: row0 = [0, *]
        for combo in itertools.product(range(n), repeat=n):
            table = []
            ok = True
            for i in range(n):
                r0 = combo[i]
                if i == 0 and r0 != 0:
                    ok = False
                    break
                row = [r0]
                # symbol 1 target chosen from all states
                for t1 in range(n):
                    table2 = [list(c) for c in table]
                    table2.append([r0, t1])
                    # fix symbol 1 by trying all at once below
                    break
                break
            break
        # simpler: enumerate full tables directly
    import itertools
    for n in range(1, 4):
        for t1s in itertools.product(range(n), repeat=n):
            left = []
            for i in range(n):
                left.append([0 if i == 0 else i, t1s[i]])
            # state 0 loops on 0; other states may go anywhere on 0
            # note: our enumeration forces row i on 0 to be i for i>0; adjust below
            for tweak in itertools.product(range(n), repeat=n):
                L = []
                good = True
                for i in range(n):
                    a = 0 if i == 0 else tweak[i]
                    L.append([a, t1s[i]])
                tr, ns, syms = _trans_of(tm)
                # try right as identity-ish: right[i][x] = i
                right = [[i, i] for i in range(n)]
                ctx = _closure_for(tm, L, right, tr, ns, syms)
                if ctx is not None:
                    cert = _emit(tm, L, right, ctx)
                    if cert:
                        return cert
    return None

def decide(tm: str) -> dict | None:
    tr, ns, syms = _trans_of(tm)
    # quick reject: if it halts within 300 steps, no certificate
    try:
        halted, steps, state, pos, tape = run(tm, 300)
        if halted:
            return None
    except Exception:
        return None
    cert = _search_side(tm, "left")
    if cert:
        return cert
    # mirror: search DFAs for the right side, use identity left
    import itertools
    for n in range(1, 4):
        for t1s in itertools.product(range(n), repeat=n):
            for tweak in itertools.product(range(n), repeat=n):
                right = []
                for i in range(n):
                    a = 0 if i == 0 else tweak[i]
                    right.append([a, t1s[i]])
                left = [[i, i] for i in range(n)]
                ctx = _closure_for(tm, left, right, tr, ns, syms)
                if ctx is not None:
                    cert = _emit(tm, left, right, ctx)
                    if cert:
                        return cert
    return None
