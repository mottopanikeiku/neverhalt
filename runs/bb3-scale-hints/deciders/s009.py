import sys
from itertools import product
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _table(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def _trans(tm):
    table, ns, nsym = parse(tm)
    out = {}
    for q in range(ns):
        for s in range(nsym):
            if (q, s) in table:
                w, m, q2 = table[(q, s)]
                out[(q, s)] = (w, m, q2)
    return out, ns, nsym


def _closure(tm, left, right, ns, nsym):
    tr, ns, nsym = _trans(tm)
    if not tr:
        return []
    ctx = {(0, 0, 0, 0)}
    seen = set(ctx)
    stack = list(ctx)
    while stack:
        l, q, s, r = stack.pop()
        if (q, s) not in tr:
            return None
        w, m, q2 = tr[(q, s)]
        if m > 0:
            if left[l][w] is None:
                return None
            l2 = left[l][w]
            for r2 in range(len(right)):
                for s2 in range(nsym):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
        else:
            if right[r][w] is None:
                return None
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in range(nsym):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
    return sorted(seen)


def _emit(tm, ctx):
    left = [[None] * 2 for _ in range(1)]
    left[0][0] = 0
    return {"kind": "cps", "left": left, "right": left, "contexts": [list(c) for c in ctx]}


def _enumerate_automata(max_states):
    out = []
    for n in range(1, max_states + 1):
        states = list(range(n))
        for combo in product(states, repeat=n * 2):
            left = [combo[i * n:(i + 1) * n] for i in range(2)]
            left = [[x if x >= 0 else None for x in row] for row in left]
            if left[0][0] != 0:
                continue
            seen = (tuple(tuple(x) if x is not None else None for x in row) for row in left)
            out.append([list(row) for row in left])
    return out


def _determinize_nfa(tr, ns, nsym, target):
    start = frozenset([0])
    trans = {}
    order = [start]
    idx = {start: 0}
    while len(order) < 2000:
        cur = order[-1]
        row = []
        for x in range(nsym):
            nxt = set()
            for q in cur:
                if (q, x) in tr:
                    _, _, q2 = tr[(q, x)]
                    nxt.add(q2)
            if nxt:
                f = frozenset(nxt)
                if f not in idx:
                    idx[f] = len(order)
                    order.append(f)
                row.append(idx[f])
            else:
                row.append(None)
        trans[idx[cur]] = [row[0] if row[0] is not None else None, row[1] if row[1] is not None else None]
        if len(order) == 2000:
            break
    return trans, order, idx


def decide(tm):
    try:
        tr, ns, nsym = _trans(tm)
    except Exception:
        return None
    if nsym != 2:
        return None
    # find halting transitions
    halting = set()
    for q in range(ns):
        for s in range(nsym):
            if (q, s) not in tr:
                halting.add((q, s))
    if not halting:
        return None
    # determine target states reachable from halting backwards
    # reverse graph
    rev = {}
    for (q, s), (w, m, q2) in tr.items():
        rev.setdefault(q2, set()).add(q)
    # states that can reach a halting transition
    can_halt = set()
    stack = []
    for (q, s) in halting:
        if q not in can_halt:
            can_halt.add(q)
            stack.append(q)
    while stack:
        q = stack.pop()
        for p in rev.get(q, ()):
            if p not in can_halt:
                can_halt.add(p)
                stack.append(p)
    if ns > 4:
        # too many states for the small search
        pass
    candidates = _enumerate_automata(2)
    for left in candidates:
        for right in candidates:
            if left[0][0] != 0 or right[0][0] != 0:
                continue
            ctx = _closure(tm, left, right, ns, nsym)
            if ctx is not None:
                # prune: automaton must not allow blank tape to be in a halting context
                # actually the closure already ensures no halting context
                cert = {"kind": "cps", "left": left, "right": right, "contexts": [list(c) for c in ctx]}
                try:
                    from neverhalt.kernel import check
                    kind = check(tm, cert)
                    return cert
                except Exception:
                    pass
    # try 3-state automata but limited
    for left in _enumerate_automata(3):
        for right in _enumerate_automata(3):
            if left[0][0] != 0 or right[0][0] != 0:
                continue
            ctx = _closure(tm, left, right, ns, nsym)
            if ctx is not None and len(ctx) <= 200000:
                cert = {"kind": "cps", "left": left, "right": right, "contexts": [list(c) for c in ctx]}
                try:
                    from neverhalt.kernel import check
                    kind = check(tm, cert)
                    return cert
                except Exception:
                    pass
    return None
} 