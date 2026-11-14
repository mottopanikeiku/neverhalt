import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse
from neverhalt.kernel import Reject

HALT = None


def closed_contexts(tm, left, right, limit=200000):
    table, n_states, n_symbols = parse(tm)
    n = n_states
    # context key: (l, q, s, r)
    seen = set()
    stack = [((0, 0, 0, 0))]
    while stack:
        if len(seen) >= limit:
            return None
        ctx = stack.pop()
        if ctx in seen:
            continue
        seen.add(ctx)
        l, q, s, r = ctx
        if q >= n or s >= n_symbols:
            continue
        t = table.get((q, s))
        if t is None:
            return None
        w, move, q2 = t
        if move == 1:
            l2 = left[l][w] if l < len(left) and w < len(left[l]) else HALT
            if l2 is HALT:
                return None
            for r2 in range(len(right)):
                row = right[r2]
                ok = False
                for s2 in range(len(row)):
                    if row[s2] == r:
                        ok = True
                        stack.append((l2, q2, s2, r2))
                if not ok:
                    continue
        else:
            r2 = right[r][w] if r < len(right) and w < len(right[r]) else HALT
            if r2 is HALT:
                return None
            for l2 in range(len(left)):
                row = left[l2]
                ok = False
                for s2 in range(len(row)):
                    if row[s2] == l:
                        ok = True
                        stack.append((l2, q2, s2, r2))
                if not ok:
                    continue
    return seen


def emit(tm, left, right, contexts):
    ltab = []
    for row in left:
        if row is None:
            ltab.append(None)
            continue
        # keep only transitions that were used
        used = {}
        for (l, q, s, r) in contexts:
            pass
        row2 = []
        for x in row:
            row2.append(x)
        ltab.append(row2)
    # prune to used transitions
    used_left = set()
    used_right = set()
    for (l, q, s, r) in contexts:
        for (ll, xx) in contexts:
            if xx is not None:
                pass
        used_left.add(l)
        used_right.add(r)
    ltab = []
    for i, row in enumerate(left):
        if row is None:
            ltab.append(None)
            continue
        new = []
        for j, v in enumerate(row):
            new.append(v)
        ltab.append(new)
    rtab = []
    for row in right:
        if row is None:
            rtab.append(None)
            continue
        rtab.append(list(row))
    ctx = sorted(contexts)
    return {"kind": "cps", "left": ltab, "right": rtab, "contexts": [[a, b, c, d] for (a, b, c, d) in ctx]}


def gen_tables(n_states, n_symbols, allow_null=True):
    # enumerate deterministic transition tables, state 0 loops on symbol 0
    choices = []
    for st in range(n_states):
        for sym in range(n_symbols):
            if st == 0 and sym == 0:
                choices.append((st, sym, [0]))
            elif allow_null:
                choices.append((st, sym, list(range(n_states)) + [HALT]))
            else:
                choices.append((st, sym, list(range(n_states))))
    idx = 0
    total = 1
    for c in choices:
        total *= len(c[2])
    while idx < total:
        tables = []
        cur = idx
        for c in choices:
            k = cur % len(c[2])
            cur //= len(c[2])
            tables.append(c[2][k])
        yield tables
        idx += 1


def normalize_left(table):
    # table: list of rows per state; row[sym] = next state or None
    # BFS canonical: start state 0
    seen = {0: 0}
    order = [0]
    i = 0
    while i < len(order):
        st = order[i]
        i += 1
        for sym in range(len(table[st])):
            if table[st][sym] is None:
                continue
            nxt = table[st][sym]
            if nxt not in seen:
                seen[nxt] = len(order)
                order.append(nxt)
        # we actually need to iterate symbols for mapping
    # build canonical table only for reachable
    n = len(seen)
    nt = []
    for st in range(n):
        row = []
        for sym in range(len(table[0])):
            v = table[st][sym]
            if v is None:
                row.append(None)
            else:
                row.append(seen[v])
        nt.append(row)
    return nt


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # quick: try 1-state then 2-state automata per side
    for n1 in (1, 2, 3):
        for n2 in (1, 2, 3):
            if n1 > n2:
                continue
            for lt in gen_tables(n1, n_symbols):
                if len(lt) != n1:
                    continue
                for rt in gen_tables(n2, n_symbols):
                    if len(rt) != n2:
                        continue
                    # enforce 0 loops on 0
                    lt[0][0] = 0
                    rt[0][0] = 0
                    # canonicalize
                    try:
                        L = normalize_left(lt)
                        R = normalize_left(rt)
                    except Exception:
                        continue
                    # enforce 0 loops
                    if not L or not R:
                        continue
                    if L[0][0] != 0 or R[0][0] != 0:
                        continue
                    if not L[0][0] == 0:
                        continue
                    # require the automaton to be total on 0 from 0
                    # check closure
                    try:
                        ctx = closed_contexts(tm, L, R, limit=200000)
                    except Exception:
                        continue
                    if ctx is None:
                        continue
                    if not ctx:
                        continue
                    # verify initial context present
                    if (0, 0, 0, 0) not in ctx:
                        continue
                    return emit(tm, L, R, ctx)
    return None


if __name__ == "__main__":
    tm = __import__("sys").argv[1]
    c = decide(tm)
    print(c) if c else print(None)