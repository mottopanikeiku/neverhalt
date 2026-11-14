import sys
from collections import deque
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _halting_states(table, n_states):
    return set(q for q in range(n_states) if (q, 0) not in table or (q, 1) not in table)


def _closure(table, n_states, left, right, dead):
    ctx = {(0, 0, 0, 0)}
    seen = ctx
    while True:
        add = set()
        for (l, q, s, r) in ctx:
            if (q, s) not in table:
                return None
            w, mv, q2 = table[(q, s)]
            if mv == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in _right_pairs(right):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        add.add(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in _left_pairs(left):
                    c = (l2, q2, s2, r2)
                    if c not in seen:
                        add.add(c)
        if not add:
            return ctx
        ctx |= add
        seen |= add
        if len(ctx) > 200000:
            return None


def _pairs(auto):
    out = []
    for i, row in enumerate(auto):
        for x, v in enumerate(row):
            if v is not None:
                out.append((i, x, v))
    return out


def _right_pairs(auto):
    return _pairs(auto)


def _left_pairs(auto):
    return _pairs(auto)


def _emit(table, n_states, left, right, ctx):
    lc = {}
    rc = {}
    for (l, q, s, r) in ctx:
        lc[(l, s)] = None
        rc[(r, s)] = None
    for l, row in enumerate(left):
        lc[l] = [row[0], row[1]]
    for r, row in enumerate(right):
        rc[r] = [row[0], row[1]]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": lc, "right": rc, "contexts": contexts}


def _auto_states(auto):
    used = set()
    for row in auto:
        for v in row:
            if v is not None:
                used.add(v)
    return used


def _small_autos():
    out = []
    for n in (1, 2, 3):
        for cells in range(1 << (2 * n)):
            rows = []
            for i in range(n):
                row = []
                for x in (0, 1):
                    row.append((cells >> (i + (x - 1) * n)) & 1 if False else None)
                rows.append(row)
            ok = True
            for i in range(n):
                for x in (0, 1):
                    bit = (cells >> (x * n + i)) & 1
                    if bit:
                        v = (cells >> (x * n + i)) & 1
                        if v:
                            rows[i][x] = None
                        else:
                            rows[i][x] = None
            out.append(rows)
    return out


def _build_auto(n, cells):
    rows = []
    for i in range(n):
        row = []
        for x in (0, 1):
            bit = (cells >> (x * n + i)) & 1
            if bit:
                row.append(None)
            else:
                row.append(None)
        rows.append(row)
    return rows


def _enumerate(n, seen):
    for cells in range(1 << (2 * n)):
        rows = []
        for i in range(n):
            row = []
            for x in (0, 1):
                bit = (cells >> (x * n + i)) & 1
                if bit:
                    row.append(None)
                else:
                    row.append(None)
            rows.append(row)
        rows[0] = [0, 0]
        key = tuple(tuple(r) for r in rows)
        if key in seen:
            continue
        seen.add(key)
        yield rows


def _cand_autos():
    seen = set()
    for n in (1, 2, 3):
        for cells in range(1 << (2 * n)):
            rows = []
            for i in range(n):
                row = []
                for x in (0, 1):
                    bit = (cells >> (x * n + i)) & 1
                    if bit:
                        row.append(None)
                    else:
                        row.append(0)
                rows.append(row)
            rows[0] = [0, 0]
            key = tuple(tuple(r) for r in rows)
            if key in seen:
                continue
            seen.add(key)
            yield rows


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    autos = list(_cand_autos())
    for la in autos:
        if la[0] != [0, 0]:
            continue
        for ra in autos:
            if ra[0] != [0, 0]:
                continue
            ctx = _closure(table, n_states, la, ra, None)
            if ctx is None:
                continue
            if len(ctx) > 200000:
                continue
            try:
                cert = _emit(table, n_states, la, ra, ctx)
                check(tm, cert)
                return cert
            except Exception:
                continue
    return None


if __name__ == "__main__":
    decide(sys.argv[1])
    print("done")
