import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Quick cycle check, cheap and often enough.
    try:
        halted, steps, state, pos, tape = run(tm, 100000)
        if halted:
            return None
        # try to find a plain cycle in the (state, pos, tape) state space is too big;
        # instead rely on CPS construction below.
    except Exception:
        return None

    # ---- Build the transition relation for a single machine state ----
    # dest[q][s] = (w, mv, q2) or None if halting
    dst = {}
    for q in range(ns):
        for s in range(nsym):
            t = table.get((q, s))
            if t is None:
                dst[(q, s)] = None
            else:
                dst[(q, s)] = (t[0], t[1], t[2])

    # ---- BFS-canonical DFA enumeration for ONE half-tape ----
    # Each automaton state is an int 0..n-1. State 0 is the blank half-tape:
    # delta[0][0] = 0 and delta[0][1] = something (usually 1).
    # We enumerate DFAs over {0,1} with n states, up to isomorphism, by
    # BFS-canonical form.  For each such DFA we build the other half-tape as
    # an NFA (reverse-determinized), then run the closed-context fixpoint.
    #
    # The context fixpoint: contexts are (l, q, s, r).  Start with (0,0,0,0).
    # For each context, the transition must be defined (else fail).  Then for
    # a right move: l2 = left[l][w] must exist; for EVERY (r2,s2) with
    # right[r2][s2] == r we need (l2, q2, s2, r2) in the set.  For a left move
    # the mirror image.  A halting transition anywhere rejects the pair.
    #
    # We prune using "backward from halting": a DFA that can read a tape
    # leading to a halt is useless.  Simpler: we just try all pairs and let
    # the fixpoint fail fast when a halting transition is reached.

    def build_cps(left, right, max_ctx=200000):
        # left: list of lists, size nL, left[i][x] in 0..nL-1 or None
        # right: same, size nR
        # contexts as a set of tuples
        ctx = set()
        ctx.add((0, 0, 0, 0))
        q = deque([(0, 0, 0, 0)])
        while q:
            if len(ctx) > max_ctx:
                return None
            l, qq, ss, rr = q.popleft()
            # transition must exist
            tr = dst.get((qq, ss))
            if tr is None:
                return None  # halting context -> reject this pair
            w, mv, q2 = tr
            if mv == +1:
                # step right: push w onto left, pop nearest right
                l2 = left[l][w] if l < len(left) and w < len(left[l]) else None
                if l2 is None:
                    return None
                # for every (r2,s2) with right[r2][s2] == rr
                for r2 in range(len(right)):
                    row = right[r2]
                    if row is None:
                        continue
                    for s2 in range(len(row)):
                        if row[s2] == rr:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                q.append(c)
            else:
                # step left: mirror
                r2 = right[rr][w] if rr < len(right) and w < len(right[rr]) else None
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    row = left[l2]
                    if row is None:
                        continue
                    for s2 in range(len(row)):
                        if row[s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                q.append(c)
        return ctx

    # ---- canonical DFA enumeration ----
    def canon_trans(delta):  # delta: tuple of tuples
        # BFS canonical labelling from state 0
        n = len(delta)
        lab = [-1] * n
        lab[0] = 0
        q = deque([0])
        while q:
            u = q.popleft()
            for sym in range(nsym):
                v = delta[u][sym]
                if v is None:
                    continue
                if lab[v] < 0:
                    lab[v] = len([x for x in lab if x >= 0])
                    q.append(v)
        # remap
        m = max(lab) + 1
        new = [None] * m
        for i in range(m):
            new[i] = [None, None]
        for u in range(n):
            nu = lab[u]
            for sym in range(nsym):
                v = delta[u][sym]
                if v is not None and lab[v] >= 0:
                    new[nu][sym] = lab[v]
        return tuple(tuple(r) for r in new)

    # Generate DFAs up to size N in canonical order via iterative deepening.
    # Simple approach: enumerate all functions delta[0..n-1][0..nsym-1] ->
    # {0..n-1} with delta[0][0] == 0, but restrict n small (<=4) and prune
    # with canonical dedup.  For n=4 and nsym=2, 4^8 = 65536 which is fine.
    # For n=5: 5^10 ~ 10M too much; we cap at 5 with delta[0][0]=0 fixing
    # one entry: 5^9 ~ 2M, still heavy but the budget is 5s; we cap at 4
    # here and rely on hashing/dedup to skip.

    NMAX = 5
    seen = set()
    count = 0

    def try_pair(left, right):
        # left, right: lists of rows (each a list of length nsym, values 0..n-1)
        ctx = build_cps(left, right)
        if ctx is None:
            return None
        # Build certificate
        left_cert = [[left[i][0], left[i][1]] for i in range(len(left))]
        right_cert = [[right[i][0], right[i][1]] for i in range(len(right))]
        contexts = [[l, qq, ss, rr] for (l, qq, ss, rr) in ctx]
        cert = {"kind": "cps", "left": left_cert, "right": right_cert, "contexts": contexts}
        try:
            check(tm, cert)
            return cert
        except Reject:
            return None

    def rows_to_lists(rows):
        return [list(r) for r in rows]

    for n in range(1, NMAX + 1):
        total = n ** (nsym * n)
        if n == 1:
            total = 1
        # iterate over all tables with delta[0][0] == 0
        import itertools
        # rows: n rows each of length nsym over 0..n-1
        # fix delta[0][0] = 0 to reduce; enumerate others
        free = []
        for i in range(n):
            for sym in range(nsym):
                if not (i == 0 and sym == 0):
                    free.append((i, sym))
        nf = len(free)
        if nf > 12:
            # too many; skip larger n
            continue
        for combo in itertools.product(range(n), repeat=nf):
            delta = [[0] * nsym for _ in range(n)]
            for (i, sym), v in zip(free, combo):
                delta[i][sym] = v
            delta[0][0] = 0
            c = canon_trans(delta)
            if c in seen:
                continue
            seen.add(c)
            count += 1
            L = rows_to_lists(c)
            # try pairing with every canonical DFA of the same size
            # (we only have 'c' here; we will re-run the outer loop to pair)
            # store for pairing phase
            # For simplicity, pair with all previously stored canonical DFAs.
            # We store them in a list `canon_list`.
            canon_list.append(L)
            for L2 in canon_list:
                cert = try_pair(L, L2)
                if cert is not None:
                    return cert

    return None