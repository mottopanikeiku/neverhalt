import itertools
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _try_cycle(tm, max_steps):
    """Try to find a translated cycle certificate by looking for a lap
    whose window content repeats shifted by d, with the outside blank."""
    from neverhalt.tm import parse as _parse
    table, n_states, n_symbols = _parse(tm)
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    if halted:
        return None
    # Re-run while recording head positions and tape snapshots at each step.
    # We record the tape as a dict; snapshot cost is okay for 500ms budgets
    # if we only snapshot at candidate lap boundaries.
    return None


def _snapshot(run_result):
    # run() returns tape as dict pos->symbol
    return None


def _try_cps(tm, max_states=3, max_steps=4000):
    table, n_states, n_symbols = parse(tm)
    states = list(range(n_states))
    syms = [0, 1]
    # Enumerate transition tables for one side with up to max_states states.
    # State 0 loops on symbol 0 (blank far away).
    # We build minimal DFAs as Python functions returning next state or None.
    def build_tables(n):
        # Each table is a tuple of n pairs (on 0, on 1) -> state or None.
        # Enumerate all assignments with state 0 on 0 = 0.
        choices = []
        for i in range(n):
            opts = []
            if i == 0:
                opts.append((0, None))  # on symbol 0 goes to 0
                # symbol 1 can be anything including None
                for x in range(n):
                    opts.append((0, x))
                for x in [None]:
                    opts.append((0, x))
            else:
                for a in range(n):
                    for b in range(n) + [None]:
                        opts.append((a, b))
            choices.append(opts)
        # Instead of naive product, we'll do BFS over reachable tables later.
        # For now generate all tables via itertools.product is too big; we
        # use a simpler enumeration: all functions from {0,1} to {0..n-1,None}
        # with state0 on 0 fixed to 0.  That is (n+1)^(2n-1) possibilities.
        def rec(i):
            if i == n:
                yield ()
                return
            for a in range(n) + [None]:
                for b in range(n) + [None]:
                    if i == 0 and a != 0:
                        continue
                    for rest in rec(i + 1):
                        yield ((a, b),) + rest
        return rec(0)

    # Context fixpoint:
    # contexts: set of (l, q, s, r)
    # Start with (0, 0, 0, 0) if it is a valid context.
    # A context is valid if transition (q,s) exists.
    # Close under: on right move q2 with write w:
    #   l2 = left[l][w] must exist, and for every r2,s2 with right[r2][s2]==r,
    #   [l2, q2, s2, r2] must be a context.
    # On left move: r2 = right[r][w] must exist, and for every l2,s2 with
    #   left[l2][s2]==l, [l2, q2, s2, r2] must be a context.
    # We do a worklist closure.
    def close(left_tab, right_tab):
        contexts = set()
        work = []
        init = (0, 0, 0, 0)
        if (0, 0) in table:  # transition exists
            contexts.add(init)
            work.append(init)
        while work:
            l, q, s, r = work.pop()
            if (q, s) not in table:
                return None  # halting context
            w, mv, q2 = table[(q, s)]
            if mv == +1:
                l2 = left_tab[l][w]
                if l2 is None:
                    return None
                # for every (r2,s2) with right_tab[r2][s2] == r
                for r2 in range(len(right_tab)):
                    for s2 in (0, 1):
                        if right_tab[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                work.append(ctx)
            else:
                r2 = right_tab[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left_tab)):
                    for s2 in (0, 1):
                        if left_tab[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                work.append(ctx)
        return contexts

    # Automata tables as list of tuples (on0, on1) with None for dead.
    def to_tab(t):
        return [tuple(x) for x in t]

    # Precompute reverse transition maps for right/left to speed up closure.
    def build_rev(tab):
        # rev[(sym, state)] = list of predecessor states p with tab[p][sym]==state
        rev = {}
        for p, (a, b) in enumerate(tab):
            for sym, nxt in ((0, a), (1, b)):
                if nxt is not None:
                    rev.setdefault((sym, nxt), []).append(p)
        return rev

    # Try all pairs of small automata.
    for n1 in range(1, max_states + 1):
        for left_t in build_tables(n1):
            left_tab = to_tab(left_t)
            if left_tab[0][0] != 0:
                continue
            for n2 in range(1, max_states + 1):
                for right_t in build_tables(n2):
                    right_tab = to_tab(right_t)
                    if right_tab[0][0] != 0:
                        continue
                    # Quick check: closure size must be <= 200000
                    ctx = close(left_tab, right_tab)
                    if ctx is None:
                        continue
                    if len(ctx) > 200000:
                        continue
                    cert = {
                        "kind": "cps",
                        "left": [list(x) for x in left_tab],
                        "right": [list(x) for x in right_tab],
                        "contexts": [list(c) for c in ctx],
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None


def decide(tm: str):
    # First attempt a translated cycle on a limited simulation.
    # run() with a large max_steps may be too slow; use a moderate one.
    try:
        cert = _try_cycle(tm, 20000)
        if cert is not None:
            return cert
    except Exception:
        pass
    try:
        cert = _try_cps(tm, max_states=3, max_steps=4000)
        if cert is not None:
            return cert
    except Exception:
        pass
    return None
