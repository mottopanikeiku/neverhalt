from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from collections import deque

NAME = "dfa_search"

def _dfa_table(n, syms, syms0, syms1, tables):
    return tables

def _all_tables(n, syms, syms0, syms1):
    # syms0: symbols allowed on the far/blank side; syms1: symbols allowed near head
    # we enumerate transition tables t[state][sym] in 0..n-1
    # state 0 must loop on 0 (blank far side) -> t[0][0] = 0
    # we require t[0][1] to be something? no: 0 loops on 0, on 1 can be any
    import itertools
    # we only enumerate tables where state 0 loops on 0
    # count: n states, 2 symbols -> 2^n per state choices
    # for n=10 this is 2^10 * 2^10 = 1e6 ... too many. we do BFS-canonical construction instead
    return None

def _canon_bfs_tables(n, syms, limit):
    # BFS over DFA transition tables with n states, canonical (minimized) form
    # state 0 loops on 0
    import itertools
    # enumerate all tables for n states
    # to keep it tractable: enumerate tables state by state with canonical BFS
    # start with all tables where t[0][0]=0, others arbitrary from 0..n-1
    # we canonicalize by computing the Myhill-Nerode equivalence via BFS over the
    # reachable state graph and only emit the smallest representative
    # Actually: enumerate all functions n x 2 -> n with t[0][0]=0
    # for n up to 10 this is n^20 which is huge.
    # So we instead do a smarter search: build DFAs by BFS over states, choosing
    # transitions one at a time; states are created lazily; we stop when we have
    # n states and all are reachable. We canonicalize by BFS-canonical naming.
    tables = []
    # represent a partial DFA as dict (state, sym) -> state
    # BFS in the space of canonical partial DFAs with at most n states
    seen = set()
    start = {}
    dq = deque([start])
    seen.add(frozenset())
    while dq:
        part = dq.popleft()
        # normalize: states are 0..k-1 where k = number of states created
        # we only add transitions for existing states
        states = sorted(set([0] + [s for (s, x) in part.keys()] + [v for v in part.values()]))
        # prune: blank tape (state 0 on all zeros) must never reach a halting state
        # no halting states here; this DFA has no halt
        if len(states) > n:
            continue
        # emit table if complete over all states
        # table: dict (state, sym) -> state
        # canonical check: renumber states by BFS from 0
        def canon(part):
            # BFS-canonical: start from state 0, order by (distance, symbol order)
            order = {}
            dq2 = deque([(0, 0)])
            order[0] = 0
            while dq2:
                s, d = dq2.popleft()
                for x in range(2):
                    if (s, x) in part:
                        v = part[(s, x)]
                        if v not in order:
                            order[v] = len(order)
                            dq2.append((v, d + 1))
            if len(order) > n:
                return None
            # renaming
            newpart = {}
            for (s, x), v in part.items():
                newpart[(order[s], x)] = order[v]
            return newpart
        c = canon(part)
        if c is None:
            continue
        key = frozenset(c.items())
        if key in seen:
            continue
        seen.add(key)
        tables.append(c)
        # extend by one transition from an existing state on either symbol
        # only add transitions to existing states or a new state (up to n)
        existing = set([s for (s, x) in c.keys()] | [v for v in c.values()])
        maxs = max(existing) if existing else 0
        for s in list(existing):
            for x in range(2):
                if (s, x) not in c:
                    # add transition to an existing state or to a brand-new state
                    for target in list(existing) + [maxs + 1]:
                        if len(set([0] + [s for (s, x) in c.keys()] + [v for v in c.values()])) + 1 > n:
                            continue
                        newpart = dict(c)
                        newpart[(s, x)] = target
                        cc = canon(newpart)
                        if cc is None:
                            continue
                        k = frozenset(cc.items())
                        if k not in seen:
                            seen.add(k)
                            dq.append(cc)
                            tables.append(cc)
        if len(tables) > limit:
            break
    return tables

def _table_to_rows(tab, n, syms):
    rows = []
    for i in range(n):
        row = []
        for x in range(2):
            v = tab.get((i, x), None)
            row.append(v)
        rows.append(row)
    return rows

def _dfa_accepts_blank(rows):
    # does the DFA accept the all-zero string? state 0 loops on 0 so yes trivially
    # we need to know if starting at state 0 and reading zeros stays in non-halting
    # our DFAs have no halting states; blank tape loops at 0 forever
    return True

def _fixpoint_contexts(tm, left_rows, right_rows, nQ, max_ctx=200000):
    # left_rows[i][x], right_rows[i][x]; cell symbol 0 or 1
    # context = (l, q, s, r)
    # start with (0,0,0,0)
    table, n_states, n_symbols = parse(tm)
    Q = n_states
    # if the DFA has no transition on a symbol -> None
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        l, q, s, r = frontier.popleft()
        if (l, q, s, r) not in ctx:
            continue
        tr = table.get((q, s))
        if tr is None:
            # halting context -> reject
            return None
        w, move, q2 = tr
        if move == 1:
            l2 = left_rows[l][w] if l < len(left_rows) and w < len(left_rows[l]) else None
            if l2 is None:
                return None
            # for every (r2, s2) with right_rows[r2][s2] == r
            for r2 in range(len(right_rows)):
                for s2 in range(2):
                    if right_rows[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            if len(ctx) >= max_ctx:
                                return None
                            ctx.add(c)
                            frontier.append(c)
        else:
            r2 = right_rows[r][w] if r < len(right_rows) and w < len(right_rows[r]) else None
            if r2 is None:
                return None
            for l2 in range(len(left_rows)):
                for s2 in range(2):
                    if left_rows[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            if len(ctx) >= max_ctx:
                                return None
                            ctx.add(c)
                            frontier.append(c)
    # emit certificate
    left = [[None if v is None else v for v in row] for row in left_rows]
    right = [[None if v is None else v for v in row] for row in right_rows]
    contexts = [[list(c) for c in ctx]]
    contexts = [list(c) for c in ctx]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    return cert

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    if n_symbols != 2:
        return None
    Q = n_states
    # try small DFA sizes first
    for n in range(1, 5):
        tables = _canon_bfs_tables(n, 2, 3000)
        for tab in tables:
            rows = _table_to_rows(tab, n, 2)
            # left DFA: reads cells far-to-head, so symbol 0 loops at 0
            # require state 0 loops on 0 (blank far side stays blank)
            if rows[0][0] != 0:
                continue
            for m in range(1, 5):
                tables2 = _canon_bfs_tables(m, 2, 3000)
                for tab2 in tables2:
                    rows2 = _table_to_rows(tab2, m, 2)
                    if rows2[0][0] != 0:
                        continue
                    cert = _fixpoint_contexts(tm, rows, rows2, Q)
                    if cert is not None:
                        try:
                            from neverhalt.kernel import check
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None
