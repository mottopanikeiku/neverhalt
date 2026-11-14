from neverhalt.tm import parse, run
from neverhalt.helpers import closure


def _build_automata(k):
    tables = []
    for n in (1, 2, 3):
        states = list(range(n))
        for mask in range((n + 1) ** 2):
            tbl = []
            for i in range(n):
                row = []
                for x in range(2):
                    idx = 2 * i + x
                    if 2 * i + x < 2 * n:
                        v = (mask >> idx) & n
                    else:
                        v = 0
                    row.append(v)
                tbl.append(row)
            if tbl[0][0] != 0:
                continue
            tables.append((n, tuple(tuple(r) for r in tbl)))
    return tables


def _push(factory):
    def push(state, symbol):
        n, tbl = factory
        return tbl[state][symbol]
    return push


def decider(tm):
    tables = _build_automata(3)
    seen = set()
    used = {}
    blank = {}
    for n in (1, 2, 3):
        for b in range(n):
            blank[(n, b)] = b
    for i, (n, tbl) in enumerate(tables):
        for j, (m, tbl2) in enumerate(tables):
            if i > j:
                continue
            key = (n, tbl, m, tbl2)
            if key in seen:
                continue
            seen.add(key)
            try:
                cert = closure(_push((n, tbl)), _push((m, tbl2)), blank[(n, 0)], blank[(m, 0)])
            except Exception:
                cert = None
            if cert is None:
                continue
            return cert
    return None