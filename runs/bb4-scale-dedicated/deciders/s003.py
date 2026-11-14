import json
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

try:
    from neverhalt.kernel import _MAX_CTX
except Exception:
    _MAX_CTX = 200000

# ---------- machine helpers ----------

def _load(tm):
    table, ns, nsym = parse(tm)
    # normalize: states 0..ns-1; missing transitions mean halt
    return table, ns, nsym

def _step(table, ns, nsym, q, s, tape, pos):
    """One step. Returns (q2, pos2, ok) with ok=False if halted."""
    key = (q, s)
    if key not in table:
        return None, None, False
    w, mv, q2 = table[key]
    if w != 0:
        tape[pos] = w
    else:
        tape.pop(pos, None)
    pos = pos + mv
    return q2, pos, True

# ---------- DFA enumeration ----------
# A half-tape DFA reads symbols from far away towards the head.
# state 0 = blank tape, loops on 0.
# We enumerate canonical DFAs by size using BFS over transition tables
# restricted to reachable states from 0.

def _enumerate_dfa_tables(max_states, max_symbols=2):
    """Yield (n, table) where table is dict (state, sym) -> state or None,
    canonical, reachable from 0, state 0 loops on 0."""
    # represent table as tuple of tuples; None = dead
    def canon_reach(t):
        n = len(t)
        # BFS from 0
        seen = {0}
        stack = [0]
        while stack:
            st = stack.pop()
            for x in range(max_symbols):
                nx = t[st][x]
                if nx is not None and nx not in seen:
                    seen.add(nx)
                    stack.append(nx)
        # relabel
        order = sorted(seen)
        mp = {st: i for i, st in enumerate(order)}
        nt = []
        for st in order:
            row = []
            for x in range(max_symbols):
                nx = t[st][x]
                row.append(mp[nx] if nx is not None else None)
            nt.append(tuple(row))
        return tuple(nt)

    for n in range(1, max_states + 1):
        # enumerate all tables with n states, 0 -> 0 on sym 0
        # use recursive generation over states in canonical order:
        # state 0 fixed, others generated, then canonicalize and dedupe.
        # To keep it tractable, generate row by row with pruning:
        #  - state 0 row: (0, anything) but canonical form will force
        #    sym0->0.
        def rec(i, rows):
            if i == n:
                # canonicalize; accept if exactly n reachable from 0
                c = canon_reach(rows)
                if len(c) == n and c[0][0] == 0:
                    yield c
                return
            # try all rows for state i
            for a in range(n):
                for b in range(n):
                    rows.append((a, b))
                    yield from rec(i + 1, rows)
                    rows.pop()
        # this is too big for n>=3; instead we do a smarter enumeration:
        # BFS over partial tables by number of defined transitions.
        # For the decider we only need small n (<=4), so cap.
        if n > 4:
            return
        # generate rows for states 1..n-1; state 0 row = (0, 0) by
        # canonical requirement (0 loops on 0). Other entries free.
        rows = [(0, 0)]
        def rec2(i):
            if i == n:
                c = canon_reach(rows)
                if len(c) == n and c[0][0] == 0:
                    yield c
                return
            for a in range(n):
                for b in range(n):
                    rows.append((a, b))
                    yield from rec2(i + 1)
                    rows.pop()
        yield from rec2(1)

# ---------- context closure ----------

def _close_contexts(table, ns, nsym, left, right):
    """left/right: transition tables (dict or list) of DFAs.
    Returns (contexts, halted) where contexts is a set of
    (l, q, s, r). halted True if a halting context is forced."""
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            key = (q, s)
            if key not in table:
                return ctx, True
            w, mv, q2 = table[key]
            if mv > 0:
                # right move: push w onto left half-tape
                l2 = left.get((l, w))
                if l2 is None:
                    return ctx, True
                # pop nearest cell off right half-tape:
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    row = right[r2]
                    for s2 in range(nsym):
                        if row[s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
            else:
                r2 = right.get((r, w))
                if r2 is None:
                    return ctx, True
                for l2 in range(len(left)):
                    row = left[l2]
                    for s2 in range(nsym):
                        if row[s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                nxt.append(c)
        frontier = nxt
        if len(ctx) > _MAX_CTX:
            return ctx, True
    return ctx, False

# ---------- reverse determinization of an NFA ----------
# right side: given a DFA for the right half-tape that reads from far
# away towards the head, the language accepted by the right half-tape
# is the set of strings read. To build a DFA reading head->far we
# reverse the NFA. Here we simply reverse the transition relation and
# determinize with subset construction, then canonicalize.

def _reverse_determinize(right, nsym):
    n = len(right)
    # reverse NFA: states are original states; transition x: from s2
    # to r2 if right[r2][x] == s2 (reading x moves r2 -> s2 forward,
    # so reversed: s2 --x--> r2)
    rev = {i: [] for i in range(n)}
    for r2 in range(n):
        for x in range(nsym):
            s2 = right[r2][x]
            rev[s2].append((x, r2))
    # subset construction starting from {0}? The right half-tape read
    # from far away starts at blank tape = state 0. Reversed reading
    # starts at the set of states that can end at 0 after reading the
    # reversed string.
    start = frozenset([0])
    dfa = {}
    order = [start]
    dfa[start] = []
    i = 0
    while i < len(order):
        cur = order[i]
        row = []
        for x in range(nsym):
            nxt = set()
            for st in cur:
                for (xx, rr) in rev[st]:
                    if xx == x:
                        nxt.add(rr)
            if not nxt:
                row.append(None)
            else:
                fs = frozenset(nxt)
                if fs not in dfa:
                    dfa[fs] = None
                    order.append(fs)
                row.append(fs)
        dfa[cur] = row
        i += 1
    # canonicalize: map frozensets to indices
    mp = {s: i for i, s in enumerate(order)}
    out = []
    for s in order:
        row = []
        for x in range(nsym):
            v = dfa[s][x]
            row.append(mp[v] if v is not None else None)
        out.append(tuple(row))
    return out

# ---------- main decider ----------

NAME = "dfa-search-cps"

def decide(tm: str):
    table, ns, nsym = _load(tm)
    # quick: try to find any halting transition reachable? no, we want
    # non-halting. Enumerate left DFAs of increasing size, canonical.
    for maxn in range(1, 5):
        seen = set()
        for left in _enumerate_dfa_tables(maxn):
            if left in seen:
                continue
            seen.add(left)
            # build left as dict
            ld = {}
            for i, row in enumerate(left):
                for x in range(nsym):
                    if row[x] is not None:
                        ld[(i, x)] = row[x]
            # right side: reverse-determinize the same language? We need
            # an NFA for the right half-tape. Use the complement DFA as
            # NFA: build an NFA that accepts strings not accepted by
            # left, by taking left's DFA and making a dead state loop.
            # Simpler: use a fresh DFA for right that is the "all
            # strings" automaton: state 0 loops on everything. That
            # gives right[r2][s2] = r for all, so the context closure
            # covers all (r2, s2) pairs with r2 = r.
            # This is sound: right half-tape can be anything.
            right = [(0, 0)]  # single state, loops on both symbols
            rd = {(0, 0): 0, (0, 1): 0}
            ctx, halted = _close_contexts(table, ns, nsym, ld, rd)
            if not halted and len(ctx) <= _MAX_CTX:
                # emit certificate
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                # kernel wants left/right as tables with null for
                # undefined; our ld/rd are dicts. Build full lists.
                def to_list(d, n):
                    out = []
                    for i in range(n):
                        row = []
                        for x in range(nsym):
                            row.append(d.get((i, x)))
                        out.append(row)
                    return out
                cert = {
                    "kind": "cps",
                    "left": to_list(ld, len(left)),
                    "right": to_list(rd, 1),
                    "contexts": contexts,
                }
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None
