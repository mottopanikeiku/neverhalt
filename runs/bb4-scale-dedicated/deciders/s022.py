from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from itertools import product

M = (1, 1, -1, 1)


def _trans(tm):
    table, ns, _ = parse(tm)
    return table, ns


def _closure(table, ns, left, right, q0=0, s0=0):
    nsl = len(left)
    nsr = len(right)
    seen = set()
    stack = [(0, 0, 0, 0)]
    seen.add((0, 0, 0, 0))
    contexts = []
    while stack:
        l, q, s, r = stack.pop()
        if q >= ns:
            continue
        t = table.get((q, s))
        if t is None:
            return None
        w, mv, q2 = t
        contexts.append((l, q, s, r))
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(nsr):
                if right[r2][w] == r:
                    key = (l2, q2, w, r2)
                    if key not in seen:
                        seen.add(key)
                        stack.append(key)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(nsl):
                if left[l2][w] == l:
                    key = (l2, q2, w, r2)
                    if key not in seen:
                        seen.add(key)
                        stack.append(key)
    return contexts


def _build(left, right, ns, table, q0=0, s0=0):
    ctx = _closure(table, ns, left, right, q0, s0)
    if ctx is None:
        return None
    lc = [[None] * 2 for _ in range(len(left))]
    rc = [[None] * 2 for _ in range(len(right))]
    for i in range(len(left)):
        for x in (0, 1):
            lc[i][x] = left[i][x]
    for i in range(len(right)):
        for x in (0, 1):
            rc[i][x] = right[i][x]
    return {"kind": "cps", "left": lc, "right": rc, "contexts": [[c[0], c[1], c[2], c[3]] for c in ctx]}


def _all_tables(n, nsl, nsr):
    for left in product(range(nsl), repeat=nsl * 2):
        if left[0] != 0:
            continue
        lt = [left[2 * i:2 * i + 2] for i in range(nsl)]
        for right in product(range(nsr), repeat=nsr * 2):
            if right[0] != 0:
                continue
            rt = [right[2 * i:2 * i + 2] for i in range(nsr)]
            yield lt, rt


def decide(tm):
    table, ns = _trans(tm)
    for nsl in (1, 2, 3, 4):
        for nsr in (1, 2, 3, 4):
            for lt, rt in _all_tables(2, nsl, nsr):
                cert = _build(lt, rt, ns, table)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None


if __name__ == "__main__":
    import sys
    for tm in sys.argv[1:]:
        c = decide(tm)
        print(tm, "OK" if c else "none")
