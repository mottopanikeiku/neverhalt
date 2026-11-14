import itertools
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

NAME = "small-dfa-cps"

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    ns = n_states
    trans = {}
    for q in range(ns):
        for s in range(2):
            t = table.get((q, s))
            if t is None:
                trans[(q, s)] = None
            else:
                w, mv, q2 = t
                trans[(q, s)] = (w, mv, q2)

    def enum_dfa_tables(max_states):
        states = list(range(max_states))
        choices = []
        for st in states:
            opts = [(nx0, nx1) for nx0 in states + [None] for nx1 in states + [None]]
            choices.append(opts)
        for combo in itertools.product(*choices):
            tbl = [[combo[st][0], combo[st][1]] for st in states]
            if tbl[0][0] != 0:
                continue
            yield tuple((a, b) for a, b in tbl)

    def closure(L, R):
        nl = len(L); nr = len(R)
        S = set()
        S.add((0, 0, 0, 0))
        stack = [(0, 0, 0, 0)]
        while stack:
            l, q, s, r = stack.pop()
            t = trans.get((q, s))
            if t is None:
                return None
            w, mv, q2 = t
            if mv > 0:
                l2 = L[l][w]
                if l2 is None:
                    return None
                for r2 in range(nr):
                    for s2 in (0, 1):
                        if R[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in S:
                                S.add(ctx); stack.append(ctx)
                                if len(S) > 200000:
                                    return None
            else:
                r2 = R[r][w]
                if r2 is None:
                    return None
                for l2 in range(nl):
                    for s2 in (0, 1):
                        if L[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in S:
                                S.add(ctx); stack.append(ctx)
                                if len(S) > 200000:
                                    return None
        return S

    max_states = 3
    for nl in range(1, max_states + 1):
        for L in enum_dfa_tables(nl):
            for nr in range(1, max_states + 1):
                for R in enum_dfa_tables(nr):
                    S = closure(L, R)
                    if S is None:
                        continue
                    left = [[L[i][0], L[i][1]] for i in range(nl)]
                    right = [[R[i][0], R[i][1]] for i in range(nr)]
                    contexts = [[l, q, s, r] for (l, q, s, r) in S]
                    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None
}