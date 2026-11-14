From neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
import sys
from itertools import product

HALT = None

def build_tables(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym

def is_halt(table, q, s):
    key = (q, s)
    if key not in table:
        return True
    w, mv, q2 = table[key]
    if q2 is None:
        return True
    if not (0 <= q2 < table_max_states(table)):
        return True
    return False

def table_max_states(table):
    m = 0
    for (q, s), v in table.items():
        q2 = v[2]
        if q2 is not None and isinstance(q2, int) and q2 >= 0:
            m = max(m, q2 + 1)
    return m

def context_closure(tm):
    table, ns, nsym = parse(tm)
    # build list of transitions
    trans = {}
    for (q, s), (w, mv, q2) in table.items():
        if q2 is None:
            trans[(q, s)] = ('halt', w, mv)
        else:
            trans[(q, s)] = ('go', w, mv, q2)
    return table, ns

def enumerate_automata(max_states):
    # returns list of (n, table) where table[i][x] = j or None, state 0 loops on 0
    for n in range(1, max_states + 1):
        for combo in product(range(n), repeat=2 * n):
            tbl = [[combo[2 * i], combo[2 * i + 1]] for i in range(n)]
            # state 0 loops on 0
            if tbl[0][0] != 0:
                continue
            # determinism: no further constraint beyond table entries
            yield n, tbl

def closure_for_pair(tm, left, right):
    table, ns = parse(tm)
    # normalize transitions
    tr = {}
    for (q, s), (w, mv, q2) in table.items():
        tr[(q, s)] = (w, mv, q2)
    # context: (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = set([start])
    stack = [start]
    contexts = set([start])
    while stack:
        (l, q, s, r) = stack.pop()
        if (q, s) not in tr:
            return None  # halting context
        w, mv, q2 = tr[(q, s)]
        if q2 is None:
            return None
        if mv == 1:
            # right move: l2 = left[l][w]; must be not null
            if l >= len(left) or w >= len(left[0]):
                return None
            l2 = left[l][w]
            if l2 is None:
                return None
            # for every pair (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                if r2 >= len(right):
                    continue
                for s2 in range(len(right[r2])):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            stack.append(ctx)
        else:
            # left move: r2 = right[r][w]
            if r >= len(right) or w >= len(right[0]):
                return None
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(len(left[l2])):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            stack.append(ctx)
    # all reachable contexts must be non-halting (checked in loop)
    # convert to output format
    left_out = [[x if x is not None else None for x in row] for row in left]
    right_out = [[x if x is not None else None for x in row] for row in right]
    ctx_out = [[l, q, s, r] for (l, q, s, r) in contexts]
    # limit sizes
    if len(ctx_out) > 200000:
        return None
    if len(left_out) > 5000 or len(right_out) > 5000:
        return None
    return {'kind': 'cps', 'left': left_out, 'right': right_out, 'contexts': ctx_out}

def decide(tm):
    # quick check with ngram-like small automata
    table, ns, nsym = parse(tm)
    # We enumerate automata up to 2 states first, then 3
    for maxn in (1, 2, 3):
        for nL, left in enumerate_automata(maxn):
            for nR, right in enumerate_automata(maxn):
                cert = closure_for_pair(tm, left, right)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None
