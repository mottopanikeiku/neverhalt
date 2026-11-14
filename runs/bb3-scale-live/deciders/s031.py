import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _tuple_state(x):
    return tuple(x)


def _norm_table(t):
    return {k: (v[0], v[1], v[2]) for k, v in t.items()}


def _run_steps(tm, n):
    table, ns, nc = parse(tm)
    tape = {}
    st = 0
    pos = 0
    for _ in range(n):
        key = (st, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, nxt = table[key]
        if w:
            tape[pos] = w
        else:
            tape.pop(pos, None)
        pos += mv
        st = nxt
    return st, pos, tape


def _build_contexts(tm, cap=200000):
    table, ns, nc = parse(tm)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier and len(ctx) < cap:
        newf = []
        for (l, q, s, r) in frontier:
            key = (q, s)
            if key not in table:
                return None
            w, mv, q2 = table[key]
            if mv > 0:
                l2 = _L[l].get(w)
                if l2 is None:
                    return None
                for (r2, s2) in _R_TARGETS[r]:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        newf.append(c)
            else:
                r2 = _R[r].get(w)
                if r2 is None:
                    return None
                for (l2, s2) in _L_TARGETS[l]:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        newf.append(c)
        frontier = newf
    if frontier:
        return None
    return ctx


def _decide(tm):
    table, ns, nc = parse(tm)
    # n-gram left/right automata, n up to 12
    global _L, _R, _L_TARGETS, _R_TARGETS
    for n in range(1, 13):
        _L = {}
        _R = {}
        _L_TARGETS = {}
        _R_TARGETS = {}
        for side in (0, 1):
            trans = _L if side == 0 else _R
            tg = _L_TARGETS if side == 0 else _R_TARGETS
            trans[()] = 0
            tg[0] = [()]  # placeholder replaced below
        # rebuild properly
        _L = {}
        _R = {}
        _L_TARGETS = {}
        _R_TARGETS = {}
        for side in (0, 1):
            trans = _L if side == 0 else _R
            tg = _L_TARGETS if side == 0 else _R_TARGETS
            trans[()] = 0
            tg[0] = [()]
        # Build all n-gram states reachable, using closure over prepended/appended symbols
        for side in (0, 1):
            trans = _L if side == 0 else _R
            tg = _L_TARGETS if side == 0 else _R_TARGETS
            seen = {(): 0}
            stack = [()]
            while stack:
                g = stack.pop()
                i = seen[g]
                for x in (0, 1):
                    if len(g) < n:
                        ng = ((x,) + g)
                        if ng not in seen:
                            seen[ng] = len(seen)
                            stack.append(ng)
                        elif len(g) == n - 1:
                            j = seen[ng]
                            if i not in tg.get(j, []):
                                tg.setdefault(j, []).append(i)
                    else:
                        # full n-gram: pop oldest, prepend x
                        ng = ((x,) + g[:-1])
                        if ng not in seen:
                            seen[ng] = len(seen)
                            stack.append(ng)
                        j = seen[ng]
                        if i not in tg.get(j, []):
                            tg.setdefault(j, []).append(i)
            trans = seen
            # reverse targets: for each j, list of i such that trans[i][x] = j
        # fix targets: recompute from final trans
        for side in (0, 1):
            trans = _L if side == 0 else _R
            tg = _L_TARGETS if side == 0 else _R_TARGETS
            tg.clear()
            for i, g in trans.items():
                for x in (0, 1):
                    if len(g) < n:
                        ng = ((x,) + g)
                    else:
                        ng = ((x,) + g[:-1])
                    j = trans.get(ng)
                    if j is not None:
                        tg.setdefault(j, []).append(i)
        ctx = _build_contexts(tm)
        if ctx is None:
            continue
        if len(ctx) > 200000:
            continue
        left_list = [[None, None] for _ in range(len(_L))]
        right_list = [[None, None] for _ in range(len(_R))]
        for i, g in _L.items():
            for x in (0, 1):
                ng = ((x,) + g) if len(g) < n else ((x,) + g[:-1])
                j = _L.get(ng)
                if j is not None:
                    left_list[i][x] = j
        for i, g in _R.items():
            for x in (0, 1):
                ng = ((x,) + g) if len(g) < n else ((x,) + g[:-1])
                j = _R.get(ng)
                if j is not None:
                    right_list[i][x] = j
        contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
        cert = {
            "kind": "cps",
            "left": left_list,
            "right": right_list,
            "contexts": contexts,
        }
        try:
            check(tm, cert)
            return cert
        except Reject:
            continue
        except Exception:
            continue
    return None


def decide(tm: str):
    return _decide(tm)
