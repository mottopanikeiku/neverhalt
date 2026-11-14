import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

sys.setrecursionlimit(1000000)

CACHE = {}


def _trans(tm, q, s):
    try:
        t = parse(tm)[0]
    except Exception:
        return None
    return t.get((q, s))


def _machine(tm):
    if tm in CACHE:
        return CACHE[tm]
    table, n_states, n_symbols = parse(tm)
    CACHE[tm] = (table, n_states, n_symbols)
    return table, n_states, n_symbols


def _closure(tm, left, right, n_states, context_limit=200000):
    table, _, _ = _machine(tm)
    cur = [[0, 0, 0, 0]]
    seen = set([(0, 0, 0, 0)])
    bad = False
    while cur and len(seen) < context_limit:
        nxt = []
        for (l, q, s, r) in cur:
            tr = table.get((q, s))
            if tr is None:
                bad = True
                return None
            w, mv, q2 = tr
            if mv == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in _right_pairs(right, r):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in seen:
                        seen.add(ctx)
                        nxt.append(ctx)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in _left_pairs(left, r):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in seen:
                        seen.add(ctx)
                        nxt.append(ctx)
        cur = nxt
    if bad:
        return None
    return sorted(seen)


def _left_pairs(left, r):
    out = []
    for i in range(len(left)):
        row = left[i]
        for x in (0, 1):
            if row[x] == r:
                out.append((i, x))
    return out


def _right_pairs(right, r):
    out = []
    for i in range(len(right)):
        row = right[i]
        for x in (0, 1):
            if row[x] == r:
                out.append((i, x))
    return out


def _emit(tm, left, right, contexts):
    table, n_states, n_symbols = _machine(tm)
    lc = [[None, None] for _ in range(len(left))]
    for i, row in enumerate(left):
        for x in (0, 1):
            if row[x] is not None:
                lc[i][x] = row[x]
    rc = [[None, None] for _ in range(len(right))]
    for i, row in enumerate(right):
        for x in (0, 1):
            if row[x] is not None:
                rc[i][x] = row[x]
    lctx = []
    for (l, q, s, r) in contexts:
        if l >= len(lc) or r >= len(rc):
            return None
        lctx.append([l, q, s, r])
    return {
        "kind": "cps",
        "left": lc,
        "right": rc,
        "contexts": lctx,
    }


def _ngram_automata(tm, n):
    table, n_states, n_symbols = _machine(tm)
    base = [None] * (1 << n)
    for i in range(1 << n):
        base[i] = i
    left = [[0, 0] for _ in range(1 << n)]
    right = [[0, 0] for _ in range(1 << n)]
    for i in range(1 << n):
        for x in (0, 1):
            hi = (i << 1) | x
            if hi >= (1 << n):
                hi = x
            left[i][x] = hi
            right[i][x] = hi
    return left, right


def decide(tm):
    try:
        table, n_states, n_symbols = _machine(tm)
    except Exception:
        return None
    # n-gram attempts first
    for n in range(0, 4):
        try:
            left, right = _ngram_automata(tm, n)
            ctx = _closure(tm, left, right, n_states)
            if ctx is not None and ctx:
                cert = _emit(tm, left, right, ctx)
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
        except Exception:
            pass
    # 1-state and 2-state search per side, blank-loop on symbol 0
    def build(states):
        rows = []
        for i in range(states):
            row = [0 if i == 0 else None, None]
            rows.append(row)
        return rows
    for states in (1, 2):
        for bits in range(1 << (states * 2)):
            left = []
            ok = True
            for i in range(states):
                row = []
                for x in (0, 1):
                    b = (bits >> (i * 2 + x)) & 1
                    row.append(b if i == 0 or b else None)
                left.append(row)
            for rbits in range(1 << (states * 2)):
                right = []
                for i in range(states):
                    row = []
                    for x in (0, 1):
                        b = (rbits >> (i * 2 + x)) & 1
                        row.append(b if i == 0 or b else None)
                    right.append(row)
                try:
                    ctx = _closure(tm, left, right, n_states)
                except Exception:
                    continue
                if ctx is None or not ctx:
                    continue
                cert = _emit(tm, left, right, ctx)
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None
