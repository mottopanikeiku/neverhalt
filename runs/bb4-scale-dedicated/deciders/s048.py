import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- helpers ----------

def table_of(tm):
    t, ns, nsym = parse(tm)
    return t, ns

def trans(t, q, s):
    return t.get((q, s))

# ---------- DFA search ----------

def _canon(states, delta, start):
    # BFS-canonical numbering of reachable states
    idx = {start: 0}
    order = [start]
    d = [dict() for _ in range(len(states))]
    i = 0
    while i < len(order):
        st = order[i]
        row = d[i]
        for sym in (0, 1):
            nxt = delta(st, sym)
            if nxt not in idx:
                idx[nxt] = len(order)
                order.append(nxt)
            row[sym] = idx[nxt]
        i += 1
    n = len(order)
    out = [[0, 0] for _ in range(n)]
    for i in range(n):
        st = order[i]
        for sym in (0, 1):
            out[i][sym] = idx[delta(st, sym)]
    return out

def all_dfas(max_states=4):
    """Yield DFA transition tables (list of [d0,d1]) over {0,1}, canonical,
    with up to max_states states, state 0 = blank loop on 0."""
    seen = set()
    frontier = [[]]
    # represent a partial table as list of rows; None means unassigned
    def rec(rows, budget):
        # rows: list of [a,b] with ints or None
        if len(rows) > budget:
            return
        # find first None
        pos = None
        for i, r in enumerate(rows):
            for j in (0, 1):
                if r[j] is None:
                    pos = (i, j)
                    break
            if pos:
                break
        if pos is None:
            if len(rows) > 1:
                # canonicalize
                canon = _canon(rows, lambda st, sym: rows[st][sym], 0)
                key = tuple(tuple(r) for r in canon)
                if key not in seen:
                    seen.add(key)
                    yield canon
            return
        i, j = pos
        for v in range(len(rows) + 1):
            nr = [list(r) for r in rows]
            nr[i][j] = v
            # prune: state 0 must loop on 0 -> blank tape stays blank
            if i == 0 and j == 0 and v != 0:
                continue
            yield from rec(nr, budget)
    # iterative deepening on number of states
    for n in range(1, max_states + 1):
        start = [[0 if (i == 0 and j == 0) else None for j in (0, 1)] for i in range(n)]
        yield from rec(start, n)

def reverse_nfa_from_table(t, ns, nsym):
    """Halting-reachable analysis: compute set of (q, s) that can reach a halt.
    Return frozenset of such pairs."""
    # transitions: (q,s) -> (w, move, q2) ; halting if absent
    # backward: a pair is bad if transition absent (halt) or some successor bad
    # We only need reachability of 'halt' via forward steps, but for DFA
    # construction we approximate: bad if it can reach a missing transition.
    bad = set()
    changed = True
    # start: pairs with no transition
    for q in range(ns):
        for s in range(nsym):
            if (q, s) not in t:
                bad.add((q, s))
    # forward closure: if (q,s) leads to (q2, s2) and (q2,s2) bad then (q,s) bad
    # build reverse edges
    rev = {}
    for (q, s), (w, mv, q2) in t.items():
        rev.setdefault((q2, w), []).append((q, s))
    stack = list(bad)
    while stack:
        cur = stack.pop()
        for pre in rev.get(cur, []):
            if pre not in bad:
                bad.add(pre)
                stack.append(pre)
    return frozenset(bad)

# ---------- context closure ----------

def closure(left, right, ns, nsym, t):
    """Compute smallest closed context set containing [0,0,0,0].
    Returns (set_of_contexts, ok) where ok means no halting context needed.
    left/right: automaton tables (list of [l0,l1]).
    """
    nL = len(left)
    nR = len(right)
    # map from (l, q, s, r) -> True
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        l, q, s, r = frontier.pop()
        tr = t.get((q, s))
        if tr is None:
            return ctx, False  # halting context
        w, mv, q2 = tr
        if mv > 0:
            # right move: push w onto left automaton, pop right
            l2 = left[l][w]
            if l2 is None:
                return ctx, False
            # r2, s2 with right[r2][s2] == r
            for r2 in range(nR):
                for s2 in range(nsym):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return ctx, False
            for l2 in range(nL):
                for s2 in range(nsym):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
    return ctx, True

def build_cps_cert(tm):
    t, ns = table_of(tm)
    nsym = 2
    bad = reverse_nfa_from_table(t, ns, nsym)
    # For speed, precompute automata list once
    # Cache across calls via module-level
    global _AUTOS
    try:
        autos = _AUTOS
    except NameError:
        autos = []
        for n in (1, 2, 3, 4):
            for d in all_dfas(max_states=n):
                autos.append(d)
        _AUTOS = autos
    # try pairs
    for left in autos:
        for right in autos:
            ctx, ok = closure(left, right, ns, nsym, t)
            if ok:
                # build certificate, keep only used transitions
                usedL = set()
                usedR = set()
                contexts = []
                for (l, q, s, r) in ctx:
                    contexts.append([l, q, s, r])
                    # we don't trim here; kernel accepts full tables
                # trim automata to used states
                def trim(aut, used):
                    # remap states appearing in used (as l or r for left)
                    # simpler: keep original size; kernel limit 5000 ok
                    return [list(row) for row in aut]
                cert = {
                    "kind": "cps",
                    "left": trim(left, None),
                    "right": trim(right, None),
                    "contexts": contexts,
                }
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

_DECIDERS = []

def decide(tm: str):
    # quick cycle check first (cheap)
    try:
        from neverhalt.tm import run
        halted, steps, state, pos, tape = run(tm, 2000)
        if halted:
            return None
    except Exception:
        pass
    return build_cps_cert(tm)


if __name__ == "__main__":
    import sys
    tm = sys.argv[1] if len(sys.argv) > 1 else "1RB0RD_0LC1LC_1RA1LB_---1RC"
    c = decide(tm)
    print(c is not None)