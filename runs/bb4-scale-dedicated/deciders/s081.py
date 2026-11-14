import sys
from collections import deque

sys.setrecursionlimit(100000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

MAX_STEPS = 4000


def _run_ok(tm, steps):
    h, s, st, pos, tape = run(tm, steps)
    if h:
        return None
    return (st, pos, dict(tape), s)


def _lap(tm, st, pos, tape, t, p):
    h, s, st2, pos2, tape2 = run(tm, p)
    return (st2, pos2, dict(tape2), s, h)


def _find_cycle(tm):
    h, s, st, pos, tape = run(tm, MAX_STEPS)
    if h:
        return None
    return None


def _sym_state_pairs(tm):
    table, ns, nsym = parse(tm)
    out = []
    for q in range(ns):
        for s in (0, 1):
            key = (q, s)
            if key in table:
                w, mv, q2 = table[key]
                out.append((q, s, w, mv, q2))
    return out


def _dfa_states(n):
    return list(range(n))


def _canonical_key(table, n):
    return tuple(tuple(table[i]) for i in range(n))


def _enumerate_dfa_tables(n):
    choices = [(0, 0), (0, 1), (1, 0), (1, 1)]
    base = [0] * n
    idx = 0
    total = len(choices) ** (n * 2)
    if total > 400000:
        total = 400000
    while idx < total:
        tbl = []
        x = idx
        for i in range(n):
            row = []
            for c in range(2):
                d = x % 2
                x //= 2
                row.append(d)
            tbl.append(tuple(row))
        yield tbl
        idx += 1


def _build_closure(tm, left_tbl, right_tbl, maxlen=80):
    table, ns, nsym = parse(tm)
    trans = {}
    for q in range(ns):
        for s in (0, 1):
            key = (q, s)
            if key in table:
                w, mv, q2 = table[key]
                trans[(q, s)] = (w, mv, q2)
    left = left_tbl
    right = right_tbl

    start = (0, 0, 0, 0)
    seen = {start}
    q = deque([start])
    contexts = []
    while q:
        ctx = q.popleft()
        contexts.append(list(ctx))
        if len(contexts) > 200000:
            return None
        l, qq, s, r = ctx
        if (qq, s) not in trans:
            return None
        w, mv, q2 = trans[(qq, s)]
        if mv == 1:
            if l >= len(left) or w >= len(left[l]):
                return None
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in seen:
                            seen.add(nctx)
                            q.append(nctx)
        else:
            if r >= len(right) or w >= len(right[r]):
                return None
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in seen:
                            seen.add(nctx)
                            q.append(nctx)
    if len(seen) > 200000:
        return None
    return contexts


def _prune_table(tbl):
    used = [False] * len(tbl)
    for i, row in enumerate(tbl):
        for c in range(2):
            if row[c] != 0:
                used[row[c]] = True
    if not used[0]:
        used[0] = True
    for i, row in enumerate(tbl):
        for c in range(2):
            if row[c] not in used:
                row = list(row)
                row[c] = 0
                tbl[i] = tuple(row)
    for i in range(len(tbl)):
        if not used[i]:
            pass
    return tbl


def decide(tm: str) -> dict | None:
    try:
        table, ns, nsym = parse(tm)
        trans = {}
        for q in range(ns):
            for s in (0, 1):
                key = (q, s)
                if key in table:
                    w, mv, q2 = table[key]
                    trans[(q, s)] = (w, mv, q2)
        if not trans:
            return None

        for n in range(1, 4):
            for lt in _enumerate_dfa_tables(n):
                if len(set(lt)) > 2 * n:
                    continue
                for rt in _enumerate_dfa_tables(n):
                    if len(set(rt)) > 2 * n:
                        continue
                    if n > 1 and lt == rt:
                        pass
                    ctx = _build_closure(tm, lt, rt)
                    if ctx is not None and len(ctx) <= 1000:
                        cert = {"kind": "cps",
                                "left": [list(r) for r in lt],
                                "right": [list(r) for r in rt],
                                "contexts": [list(c) for c in ctx]}
                        try:
                            from neverhalt.kernel import check
                            check(tm, cert)
                            return cert
                        except Exception:
                            pass
        return None
    except Exception:
        return None


DECIDER_NAME = "small-cps-search" if False else "small-cps-search"