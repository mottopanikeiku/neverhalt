import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Automaton states are ints 0..n-1; 0 is the blank half-tape, fixed to loop on 0.
# A transition table is a dict (state, symbol) -> next state or None (undefined).
# We only ever need transitions on symbols 0 and 1.

SYMS = (0, 1)


def canon_key(table, n):
    # BFS-canonical form of a deterministic partial automaton, start state 0.
    # Always: (0,0) -> 0 (the blank tape loops).
    # Only keep transitions that are reachable and total enough to be useful.
    seen = {}
    q = deque([0])
    while q:
        s = q.popleft()
        for x in SYMS:
            t = table.get((s, x))
            if t is None:
                continue
            if t not in seen:
                seen[t] = len(seen) + 1
                q.append(t)
    # relabel reachable states in BFS order, 0 stays 0
    lab = {0: 0}
    order = deque([0])
    while order:
        s = order.popleft()
        for x in SYMS:
            t = table.get((s, x))
            if t is None:
                continue
            if t not in lab:
                lab[t] = len(lab)
                order.append(t)
    nt = {}
    for (s, x), t in table.items():
        if s in lab and t in lab:
            nt[(lab[s], x)] = lab[t]
    return frozenset(nt.items())


def enumerate_tables(nstates):
    """All tables on {0,1}^2 with nstates states, start 0, partial on 1."""
    # Represent table as tuple of length nstates*2: value in 0..nstates-1 or -1.
    if nstates == 1:
        yield {}
        return
    from itertools import product
    vals = list(range(nstates)) + [-1]
    for combo in product(vals, repeat=2 * nstates):
        table = {}
        for s in range(nstates):
            for x in SYMS:
                v = combo[2 * s + x]
                if v >= 0:
                    table[(s, x)] = v
        if table.get((0, 0)) != 0:
            continue
        yield table


def close_contexts(left, right, n_states_machine, table, max_ctx=200000):
    """Closed context set for a fixed pair of half-tape automata.
    Returns (contexts, ok) where ok means no halting context was forced.
    Context: (l, q, s, r), l in left states, r in right states, q in 0..n_states_machine-1, s in {0,1}.
    """
    # We need left[l][w] for the written symbol w and right[r][w] similarly.
    # Kernel convention: left[l][x] is the state reached from l on symbol x.
    # Our left table is oriented far-away -> head. In the kernel, "left" reads
    # cells left of the head from far away towards the head, so left[l][x] is
    # exactly our table. Same for right.
    # A context [l,q,s,r] is closed if:
    #   transition (q,s) exists (not halting)
    #   if move right: l2 = left[l][w] must exist and for every (r2,s2) with
    #       right[r2][s2] == r, context (l2, q2, s2, r2) must be in the set
    #   if move left: r2 = right[r][w] must exist and for every (l2,s2) with
    #       left[l2][s2] == l, context (l2, q2, s2, r2) must be in the set
    # We compute the fixpoint starting from the required context (0,0,0,0).
    if (0, 0) not in left or (0, 0) not in right:
        # blank tape must loop on 0
        return None, False
    # Precompute preimages for each automaton state.
    # left_pre[state] = list of (prev_state, symbol) with left[prev][symbol] == state
    # right_pre likewise.
    def preimage(table, n):
        pre = [[] for _ in range(n)]
        for (s, x), t in table.items():
            if t < n:
                pre[t].append((s, x))
        return pre
    # number of states: infer max+1
    def nstates_of(table):
        m = 0
        for (s, x), t in table.items():
            m = max(m, s, t)
        return m + 1
    nl = nstates_of(left)
    nr = nstates_of(right)
    lpre = preimage(left, nl)
    rpre = preimage(right, nr)
    # context set: use a set of tuples (l,q,s,r)
    ctx = {(0, 0, 0, 0)}
    frontier = deque([(0, 0, 0, 0)])
    while frontier:
        l, q, s, r = frontier.popleft()
        tr = table.get((q, s))
        if tr is None:
            # halting context forced -> not ok
            return None, False
        w, move, q2 = tr
        if move > 0:  # right move
            if (l, w) not in left:
                return None, False
            l2 = left[(l, w)]
            # for every (r2,s2) with right[r2][s2] == r, add (l2,q2,s2,r2)
            for (r2, s2) in rpre[r]:
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    if len(ctx) > max_ctx:
                        return None, False
                    ctx.add(c)
                    frontier.append(c)
        else:  # left move
            if (r, w) not in right:
                return None, False
            r2 = right[(r, w)]
            for (l2, s2) in lpre[l]:
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    if len(ctx) > max_ctx:
                        return None, False
                    ctx.add(c)
                    frontier.append(c)
    # No halting context was forced.
    # Convert to kernel format: left[i][x] table, right[i][x] table, contexts list.
    # Automaton tables: include all transitions used, keep 0-loop.
    def to_table(t, n):
        out = [[None, None] for _ in range(n)]
        for (s, x), v in t.items():
            if s < n and v < n:
                out[s][x] = v
        return out
    ltab = to_table(left, nl)
    rtab = to_table(right, nr)
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return (ltab, rtab, contexts), True


def try_pair(tm, table, left, right):
    tt, n_states, n_symbols = parse(tm)
    # Build transition table as dict (q,s) -> (w, move, q2)
    trans = {}
    for (q, s), (w, mv, q2) in tt.items():
        trans[(q, s)] = (w, mv, q2)
    res = close_contexts(left, right, n_states, trans)
    if res is None:
        return None
    (ltab, rtab, contexts), ok = res
    if not ok:
        return None
    cert = {"kind": "cps", "left": ltab, "right": rtab, "contexts": contexts}
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert


def decide(tm: str):
    tt, n_states, n_symbols = parse(tm)
    if n_symbols != 2:
        return None
    trans = {}
    for (q, s), (w, mv, q2) in tt.items():
        trans[(q, s)] = (w, mv, q2)
    # Search one side's automaton, then derive the other by trying a small set.
    # Here we simply enumerate pairs of small automata directly for speed.
    budget_states = 3
    for n1 in range(1, budget_states + 1):
        for left in enumerate_tables(n1):
            # try to find a right side quickly by testing a few candidates
            for n2 in range(1, budget_states + 1):
                for right in enumerate_tables(n2):
                    # quick filter: both must loop on 0
                    if left.get((0, 0)) != 0 or right.get((0, 0)) != 0:
                        continue
                    cert = try_pair(tm, trans, left, right)
                    if cert is not None:
                        return cert
    return None


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        tm = line.strip()
        if not tm:
            continue
        try:
            c = decide(tm)
            print(tm, "->", "OK" if c else "none")
        except Exception as e:
            print(tm, "-> error", e)
