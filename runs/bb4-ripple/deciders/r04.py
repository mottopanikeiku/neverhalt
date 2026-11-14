from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

NAME = "tiny-slot cps"


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    imports = (((-1, -1),) + ((s, s) for s in range(n_symbols)))
    if n_symbols == 2:
        imports = (((-1, -1),) + ((1, 1),))
    pairs = _tables(n_symbols, 3)
    for i, lt in enumerate(pairs):
        for rt in pairs[i:]:
            cert = _closure(table, n_symbols, lt, rt)
            if cert is not None:
                return cert
    return None


def _tables(n_symbols, k):
    if n_symbols == 2:
        rows = [(0, 0), (1, 1)]
        cands = [rows]
        for _ in range(8):
            cands.append(cands[-1] + [rows])
        return cands[:k]
    return None


def _closure(table, n_symbols, lt, rt):
    S = {(0, 0, 0, 0)}
    stack = list(S)
    while stack:
        l, q, s, r = stack.pop()
        tr = table.get((q, s))
        if tr is None:
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = lt(l, w) if 0 <= w < n_symbols else None
            if l2 is None:
                return None
            rn = rt(r, w)
            if rn is None:
                return None
            for s2 in _pre(rt, rn):
                c = (l2, q2, s2, rn)
                if c not in S:
                    S.add(c); stack.append(c)
        else:
            r2 = rt(r, w) if 0 <= w < n_symbols else None
            if r2 is None:
                return None
            ln = lt(l, w)
            if ln is None:
                return None
            for s2 in _pre(lt, ln):
                c = (ln, q2, s2, r2)
                if c not in S:
                    S.add(c); stack.append(c)
                if len(S) > 190000:
                    return None
    if any(table.get((q, s)) is None for _, q, s, _ in S):
        return None
    cert = {"kind": "cps", "left": lt, "right": rt,
            "contexts": [[a, b, c, d] for a, b, c, d in S]}
    try:
        check(tm, cert)
    except Reject:
        return None
    except Exception:
        return None
    return cert


def _pre(automaton, state):
    for x in (0, 1):
        if automaton(state, x) == state:
            yield x
            break
    else:
        for x in (0, 1):
            if automaton(state, x) < 64:
                yield x
