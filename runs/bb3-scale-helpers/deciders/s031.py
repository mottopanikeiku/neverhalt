from neverhalt.tm import parse
from neverhalt.kernel import Reject
from neverhalt.helpers import closure


def _states(n):
    return list(range(n))


def _gen_tables(n, symbols=(0, 1)):
    import itertools
    states = _states(n)
    total = n * len(symbols)
    for combo in itertools.product(states + [None], repeat=total):
        table = {}
        ok = True
        for i in states:
            if table.get((i, 0)) is None and table.get((i, 1)) is None:
                pass
            for j, s in enumerate(symbols):
                v = combo[i * len(symbols) + j]
                table[(i, s)] = v
        # state 0 must loop on 0
        if table[(0, 0)] != 0:
            continue
        yield table


def _push_from(table):
    def p(state, symbol):
        return table.get((state, symbol))
    return p


def decide(tm):
    parsed, n_states, n_symbols = parse(tm)
    table, _, _ = parse(tm)
    from neverhalt.tm import parse as _p
    try:
        _, _, _ = _p(tm)
    except Exception:
        return None
    try:
        for n in (1, 2, 3):
            for lt in _gen_tables(n):
                blank_l = 0
                # blank state must loop on 0
                if lt[(0, 0)] != 0:
                    continue
                for rt in _gen_tables(n):
                    if rt[(0, 0)] != 0:
                        continue
                    pl = _push_from(lt)
                    pr = _push_from(rt)
                    try:
                        cert = closure(pl, pr, blank_l, 0, cap=200000)
                    except Exception:
                        cert = None
                    if cert is None:
                        continue
                    try:
                        from neverhalt.kernel import check
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
                    except Exception:
                        continue
    except Exception:
        return None
    return None
