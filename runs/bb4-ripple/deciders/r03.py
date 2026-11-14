from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

NAME = "ngram cps"


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    for N in (4, 5, 6, 7, 8):
        cert = _build(table, n_symbols, N)
        if cert is not None:
            return cert
    return None


def _build(table, n_symbols, N):
    mask = (1 << N) - 1
    top = 1 << (N - 1)
    n_auto = 1 << N
    ctx_cap = 180000
    S = set()
    S.add((0, 0, 0, 0))
    stack = [(0, 0, 0, 0)]
    pop = stack.pop
    append = stack.append
    tget = table.get

    while stack:
        if len(S) > ctx_cap:
            return None
        l, q, s, r = pop()
        tr = tget((q, s))
        if tr is None:
            return None
        w, mv, q2 = tr
        if mv == 1:
            l2 = ((l << 1) | w) & mask
            lo = r & 1
            base = r >> 1
            c0 = (l2, q2, lo, base)
            if c0 not in S:
                S.add(c0); append(c0)
                if len(S) > ctx_cap:
                    return None
            c1 = (l2, q2, lo, base | top)
            if c1 not in S:
                S.add(c1); append(c1)
                if len(S) > ctx_cap:
                    return None
        else:
            r2 = ((r << 1) | w) & mask
            lo = l & 1
            base = l >> 1
            c0 = (base, q2, lo, r2)
            if c0 not in S:
                S.add(c0); append(c0)
                if len(S) > ctx_cap:
                    return None
            c1 = (base | top, q2, lo, r2)
            if c1 not in S:
                S.add(c1); append(c1)
                if len(S) > ctx_cap:
                    return None

    row = [[((i << 1) | x) & mask for x in range(n_symbols)] for i in range(n_auto)]
    left_t = [list(r) for r in row]
    right_t = [list(r) for r in row]
    contexts = [list(c) for c in S]
    cert = {"kind": "cps", "left": left_t, "right": right_t, "contexts": contexts}
    try:
        check(tm, cert)
    except Reject:
        return None
    except Exception:
        return None
    return cert
