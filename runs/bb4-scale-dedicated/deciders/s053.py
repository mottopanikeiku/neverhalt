from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Enumerate DFAs for a half-tape read far-to-head, state 0 = all-blank tape.
# Table: dict (state, symbol) -> next_state, with state 0 looping on 0.
# BFS-canonical order: grow the number of reachable states, prefer tables
# whose reachable state set is exactly {0..n-1} and whose transitions are
# assigned in lexicographic order.

def _dfa_states(n):
    return list(range(n))

def _closure_states(table, n):
    # reachable states from 0
    seen = {0}
    work = [0]
    while work:
        s = work.pop()
        for x in (0, 1):
            t = table.get((s, x))
            if t is not None and t not in seen:
                seen.add(t)
                work.append(t)
    return seen

def enumerate_dfa_pairs(max_states=5):
    """Yield (left_table, right_table) for small DFAs, BFS-canonical."""
    # Build all DFAs with n states where state 0 loops on 0 and the
    # reachable set is exactly {0..n-1}. Represent as tuple indexed by
    # (state*2+symbol) -> target.
    def all_dfa(n):
        out = []
        # enumerate assignments of transitions for states 1..n-1 (0 fixed: 0->0 on 0)
        # and symbol 1 for state 0
        # transitions: for state 0: on 0 -> 0, on 1 -> t00 in 0..n-1
        # for states 1..n-1: on 0 -> t, on 1 -> t
        import itertools
        # We enumerate a tuple of length n*2: index s*2+x
        # state 0 x=0 is fixed to 0.
        idxs = []
        for s in range(n):
            for x in range(2):
                if s == 0 and x == 0:
                    continue
                idxs.append((s, x))
        # values 0..n-1 each
        for vals in itertools.product(range(n), repeat=len(idxs)):
            tab = {(0, 0): 0}
            for (s, x), v in zip(idxs, vals):
                tab[(s, x)] = v
            # require reachable set exactly {0..n-1}
            reach = {0}
            work = [0]
            while work:
                s = work.pop()
                for x in (0, 1):
                    t = tab[(s, x)]
                    if t not in reach:
                        reach.add(t)
                        work.append(t)
            if reach != set(range(n)):
                continue
            out.append(tab)
        return out

    for n in range(1, max_states + 1):
        lefts = all_dfa(n)
        for lt in lefts:
            # right side: same enumeration but we only need one side's
            # table; context closure will test pairs. To keep the search
            # finite, pair each left DFA with every right DFA of the same
            # size, but that is n^n * ... too big for n>=4. Instead, for
            # each left DFA we use the same DFA as the right one first,
            # then a mirrored one. The context closure is symmetric, so
            # testing (L, R) and (R, L) both.
            for rt in lefts:
                yield lt, rt

def _context_closure(tm, left_tab, right_tab, max_ctx=200000):
    """Compute the closed context set for the given half-tape automata.

    Returns (contexts, halted) where contexts is a list of
    [l, q, s, r] and halted is True if any halting transition is
    forced.  left_tab and right_tab map (state, symbol) -> state.
    """
    table, n_states, n_symbols = parse(tm)
    # context set as a set of tuples (l, q, s, r)
    ctx = set()
    # seed with the blank tape context
    if left_tab.get((0, 0)) is not None and right_tab.get((0, 0)) is not None:
        ctx.add((0, 0, 0, 0))
    changed = True
    while changed and len(ctx) < max_ctx:
        changed = False
        for (l, q, s, r) in list(ctx):
            tr = table.get((q, s))
            if tr is None:
                return None, True  # halting context
            w, move, q2 = tr
            if move == 1:
                l2 = left_tab.get((l, w))
                if l2 is None:
                    return None, True
                # for every (r2, s2) with right_tab[(r2, s2)] == r
                for r2 in range(max(left_tab.keys(), key=lambda k: k[0])[0] + 1):
                    pass
                # collect all r2 such that some s2 maps to r
                # iterate over all known right states
                rstates = set()
                for (st, x) in right_tab:
                    rstates.add(st)
                for r2 in rstates:
                    for s2 in (0, 1):
                        if right_tab.get((r2, s2)) == r:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                changed = True
            else:
                r2 = right_tab.get((r, w))
                if r2 is None:
                    return None, True
                lstates = set()
                for (st, x) in left_tab:
                    lstates.add(st)
                for l2 in lstates:
                    for s2 in (0, 1):
                        if left_tab.get((l2, s2)) == l:
                            c = (l2, q2, s2, r2)
                            if c not in ctx:
                                ctx.add(c)
                                changed = True
    if len(ctx) >= max_ctx:
        return None, False
    # check no halting context
    for (l, q, s, r) in ctx:
        if table.get((q, s)) is None:
            return None, True
    return ctx, False

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Quick check: if the machine halts within a small number of steps,
    # this decider is not for it.
    try:
        halted, steps, state, pos, tape = run(tm, 200)
        if halted:
            return None
    except Exception:
        return None
    # Enumerate small automata.  Start with 1-state (all-blank half-tape)
    # and grow.  The context closure is cheap for tiny automata.
    max_states = 4
    for n in range(1, max_states + 1):
        # build all DFAs of size n for both sides (bounded enumeration)
        def all_dfa(n):
            import itertools
            out = []
            idxs = []
            for s in range(n):
                for x in range(2):
                    if s == 0 and x == 0:
                        continue
                    idxs.append((s, x))
            # limit the enumeration: for n>=3 this is n^(2n-1) which is
            # large; cap by preferring tables where state 0 on 1 is 0
            # (the most common surviving case) and iterate the rest.
            for vals in itertools.product(range(n), repeat=len(idxs)):
                tab = {(0, 0): 0}
                for (s, x), v in zip(idxs, vals):
                    tab[(s, x)] = v
                reach = {0}
                work = [0]
                while work:
                    s = work.pop()
                    for x in (0, 1):
                        t = tab[(s, x)]
                        if t not in reach:
                            reach.add(t)
                            work.append(t)
                if reach != set(range(n)):
                    continue
                out.append(tab)
                if len(out) >= 400:
                    break
            return out
        lefts = all_dfa(n)
        if not lefts:
            continue
        for lt in lefts:
            for rt in lefts:
                ctx, halted = _context_closure(tm, lt, rt)
                if ctx is not None and not halted:
                    # build certificate
                    left = [[None, None] for _ in range(n)]
                    right = [[None, None] for _ in range(n)]
                    for s in range(n):
                        for x in (0, 1):
                            if (s, x) in lt:
                                left[s][x] = lt[(s, x)]
                            if (s, x) in rt:
                                right[s][x] = rt[(s, x)]
                    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                    cert = {"kind": "cps", "left": left, "right": right,
                            "contexts": contexts}
                    try:
                        check(tm, cert)
                    except Reject:
                        continue
                    return cert
    return None
