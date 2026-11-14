import sys
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _halting_transitions(table):
    return [(q, s) for (q, s) in table if table.get((q, s)) is None]


def _nstates(table):
    if not table:
        return 0
    return max(max(q for (q, s) in table), max(q for (q, s) in table)) + 1


def _nsymbols(table):
    if not table:
        return 1
    return max(max(s for (q, s) in table), max(s for (q, s) in table)) + 1


def _keep_row(table, row):
    return {(q, s): v for (q, s), v in table.items() if q == row}


def _build_keep_rows(table, keep):
    return {(q, s): table[(q, s)] for (q, s) in table if q in keep}


def _ngram_cps(table, n):
    import itertools
    ns = _nsymbols(table)
    nq = _nstates(table)
    # left automaton: state 0 = all blank; state i = last i symbols seen from far to head
    def mk(state_count):
        trans = {}
        for i in range(state_count):
            for x in range(ns):
                if i == 0:
                    if x == 0:
                        trans[(0, x)] = 0
                    else:
                        trans[(0, x)] = 1
                else:
                    # state i means we have seen i-1 symbols (including blanks) from far away.
                    # we remember the last n-1 symbols; if i < n, we just extend.
                    # if i == n, we shift: new state = hash of last n symbols
                    # For simplicity of search: treat states 1..n-1 as prefixes, and n as full memory.
                    if i < n:
                        # we are still filling the window; remember x by hashing
                        h = 0
                        for k in range(i - 1):
                            h = (h * 3 + 1) % 7
                        h = (h * 3 + x) % 7
                        # we do not actually have previous symbols; this DFA is wrong in general.
                        # Instead we build a real DFA below.
                        pass
        return trans
    return None


def _dfa_from_memory(rows, ns):
    # Build DFA whose states are n-grams of the last n symbols (far to head).
    # state 0 = all blank (n zeros).
    n = len(rows)
    if n == 0:
        n = 1
    blank = (0,) * n
    start = blank
    def step(state, x):
        return (state[1:] + (x,))
    # BFS
    trans = {}
    order = []
    seen = {start: 0}
    order.append(start)
    i = 0
    while i < len(order):
        st = order[i]
        i += 1
        for x in range(ns):
            ns_st = step(st, x)
            if ns_st not in seen:
                seen[ns_st] = len(order)
                order.append(ns_st)
            trans[(len(order) - 1 if False else seen[st], x)] = seen[ns_st]
    # remap indices: state id = seen[state]
    remap = {seen[st]: i for i, st in enumerate(order)}
    out = {}
    for st, idx in remap.items():
        for x in range(ns):
            out[(idx, x)] = remap[seen[step(st, x)]]
    return out, len(order)


def _fixpoint(table, left, right, limit=200000):
    nq = _nstates(table)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        new = []
        for (l, q, s, r) in list(contexts):
            if (q, s) not in table:
                continue
            w, mv, q2 = table[(q, s)]
            if mv == 1:
                l2 = left.get((l, w))
                if l2 is None:
                    continue
                # for every pair (r2, s2) with right[r2][s2] == r
                for (r2, s2), v in right.items():
                    if v == r:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            changed = True
            else:
                r2 = right.get((r, w))
                if r2 is None:
                    continue
                for (l2, s2), v in left.items():
                    if v == l:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            changed = True
            if len(contexts) > limit:
                return None
    # check no halting context
    for (l, q, s, r) in contexts:
        if (q, s) not in table:
            return None
    # emit certificate
    left_t = {}
    for (a, b), c in left.items():
        left_t.setdefault(a, {})[b] = c
    right_t = {}
    for (a, b), c in right.items():
        right_t.setdefault(a, {})[b] = c
    rows = []
    for (l, q, s, r) in sorted(contexts):
        rows.append([l, q, s, r])
    return {"kind": "cps", "left": [[a] for a in left_t], "right": [[a] for a in right_t], "contexts": rows}


def _emit(table, left, right, contexts):
    left_list = []
    maxl = max([a for (a, b) in left] or [0]) + 1
    for i in range(maxl):
        row = []
        for x in range(_nsymbols(table)):
            row.append(left.get((i, x)))
        left_list.append(row)
    right_list = []
    maxr = max([a for (a, b) in right] or [0]) + 1
    for i in range(maxr):
        row = []
        for x in range(_nsymbols(table)):
            row.append(right.get((i, x)))
        right_list.append(row)
    rows = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left_list, "right": right_list, "contexts": rows}


def decide(tm):
    table, nq, ns = parse(tm)
    if not table:
        return None
    # try small n-gram DFAs for both half tapes
    for n in range(1, 5):
        left, nl = _dfa_from_memory(list(range(n)), ns)
        right, nr = _dfa_from_memory(list(range(n)), ns)
        res = _fixpoint(table, left, right)
        if res is not None:
            try:
                from neverhalt.kernel import check
                check(tm, res)
                return res
            except Exception:
                pass
    # try asymmetric: left n-gram, right 1-state
    for n in range(1, 5):
        left, nl = _dfa_from_memory(list(range(n)), ns)
        right = {(0, 0): 0, (0, 1): 0}
        res = _fixpoint(table, left, right)
        if res is not None:
            try:
                check(tm, res)
                return res
            except Exception:
                pass
    for n in range(1, 5):
        left = {(0, 0): 0, (0, 1): 0}
        right, nr = _dfa_from_memory(list(range(n)), ns)
        res = _fixpoint(table, left, right)
        if res is not None:
            try:
                check(tm, res)
                return res
            except Exception:
                pass
    return None
