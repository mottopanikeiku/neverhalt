import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: cps_ngram_search
# Enumerates small deterministic automata for the left/right half-tape (n-gram
# style, with some extra states for counters), computes the closed context set
# for a machine, and returns a certificate if no halting context is reachable.

def _halt_pairs(tm):
    table, n_states, n_symbols = parse(tm)
    hp = set()
    for q in range(n_states):
        for s in range(n_symbols):
            t = table.get((q, s))
            if t is None:
                hp.add((q, s))
    return hp

def _automaton_tables(max_states):
    # Yields (left_table, right_table) as lists of dicts: state -> {sym: next_state}
    # state 0 loops on symbol 0 (the all-blank half-tape).
    syms = (0, 1)
    tables = []
    for n in range(1, max_states + 1):
        # Generate all deterministic tables for n states where state 0 on 0 -> 0.
        # Represent each state's row as a pair (on0, on1) with on1 optionally None
        # (meaning that symbol never occurs in that half-tape).
        rows = []
        # state 0: on0 must be 0
        choices0 = [(0, None), (0, 1), (0, 0)]
        # state i>0: any of the n states, or None
        choices = [(i, None) for i in range(n)] + [(i, j) for i in range(n) for j in range(n)]
        # enumerate cartesian product (bounded)
        import itertools
        if n == 1:
            opts = [(0, None), (0, 1), (0, 0)]
        else:
            opts = [(0, None), (0, 1), (0, 0)]
            rest = [(i, None) for i in range(1, n)] + [(i, j) for i in range(1, n) for j in range(n)]
        # limit combinations to avoid explosion
        total = 1
        if n == 1:
            total = len(opts)
        else:
            total = len(opts) * (len(rest) ** (n - 1))
        if total > 200000:
            continue
        for combo in itertools.product(opts, rest):
            # build table
            tab = [dict() for _ in range(n)]
            ok = True
            for i in range(n):
                r = combo[0] if i == 0 else combo[i]
                on0, on1 = r
                if on0 is None:
                    ok = False
                    break
                tab[i][0] = on0
                if on1 is not None:
                    tab[i][1] = on1
            if not ok:
                continue
            if tab[0].get(0) != 0:
                continue
            tables.append(tab)
    return tables

def _closure(tm, left, right, max_contexts=200000):
    table, n_states, n_symbols = parse(tm)
    hp = _halt_pairs(tm)
    # context: (l, q, s, r)
    init = (0, 0, 0, 0)
    seen = set()
    stack = [init]
    seen.add(init)
    while stack:
        l, q, s, r = stack.pop()
        t = table.get((q, s))
        if t is None:
            return None  # halting context reached
        w, move, q2 = t
        if move == 1:
            l2 = left[l].get(w)
            if l2 is None:
                return None
            # for every (r2, s2) with right[r2].get(s2) == r
            for r2 in range(len(right)):
                row = right[r2]
                for s2, rr in row.items():
                    if rr == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r].get(w)
            if r2 is None:
                return None
            for l2 in range(len(left)):
                row = left[l2]
                for s2, ll in row.items():
                    if ll == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        if len(seen) > max_contexts:
            return None
    if len(seen) > 200000:
        return None
    return seen

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    hp = _halt_pairs(tm)
    if not hp:
        return None
    # Try n-gram style automata: remember last k cells of each half-tape.
    # State = tuple of last k symbols (or a special start state).
    for k in range(1, 4):
        # Build automaton for k-gram: state = (start) or tuple of length k
        # For simplicity: state 0 = all-blank; other states = tuple of bits.
        # We represent state as index; transitions computed on the fly.
        def build_gram(k):
            # map tuple -> index
            idx = {}
            states = []
            # state 0 reserved for blank
            def get_state(tup):
                if tup in idx:
                    return idx[tup]
                i = len(states)
                idx[tup] = i
                states.append(tup)
                return i
            # state 0: blank, on 0 -> 0, on 1 -> state for tuple (1,0,...,0)?
            # Actually for k-gram, reading symbol x shifts in x at the head side.
            # We'll build lazily via a dict of transitions.
            trans = {}
            def step(state, x):
                key = (state, x)
                if key in trans:
                    return trans[key]
                if state == 0:
                    if x == 0:
                        trans[key] = 0
                    else:
                        # shift: new tuple = (x,) + (0,)*(k-1)
                        tup = (x,) + (0,) * (k - 1)
                        trans[key] = get_state(tup)
                else:
                    tup = states[state]
                    newtup = (x,) + tup[:-1]
                    trans[key] = get_state(newtup)
                return trans[key]
            return step
        for side in ('left', 'right'):
            step = build_gram(k)
            # Build full table up to some bound
            n = 1
            tab = [dict()]
            frontier = [0]
            while frontier and n <= 200:
                nxt = []
                for st in frontier:
                    for x in (0, 1):
                        ns = step(st, x)
                        if ns >= len(tab):
                            tab.append(dict())
                        if x not in tab[st]:
                            tab[st][x] = ns
                            if ns == len(tab) - 1 and ns not in frontier:
                                nxt.append(ns)
                frontier = nxt
                n = len(tab)
            yield tab
    # We need both sides; combine smallest tables found.
    # For efficiency, try pairs from a small pool.
    pool = []
    for k in range(1, 4):
        def build_gram(k):
            idx = {}
            states = []
            def get_state(tup):
                if tup in idx:
                    return idx[tup]
                i = len(states)
                idx[tup] = i
                states.append(tup)
                return i
            trans = {}
            def step(state, x):
                key = (state, x)
                if key in trans:
                    return trans[key]
                if state == 0:
                    if x == 0:
                        trans[key] = 0
                    else:
                        tup = (x,) + (0,) * (k - 1)
                        trans[key] = get_state(tup)
                else:
                    tup = states[state]
                    newtup = (x,) + tup[:-1]
                    trans[key] = get_state(newtup)
                return trans[key]
            return step
        step = build_gram(k)
        n = 1
        tab = [dict()]
        frontier = [0]
        while frontier and n <= 300:
            nxt = []
            for st in frontier:
                for x in (0, 1):
                    ns = step(st, x)
                    if ns >= len(tab):
                        tab.append(dict())
                    if x not in tab[st]:
                        tab[st][x] = ns
                        if ns == len(tab) - 1 and ns not in frontier:
                            nxt.append(ns)
            frontier = nxt
            n = len(tab)
        pool.append(tab)
    # Try all pairs (including same table for both sides)
    for left in pool:
        for right in pool:
            if len(left) > 200 or len(right) > 200:
                continue
            ctx = _closure(tm, left, right)
            if ctx is None:
                continue
            # Build context list
            contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
            cert = {
                "kind": "cps",
                "left": [[a, b] for a in left for b in sorted(left[a].items())],
                "right": [[a, b] for a in right for b in sorted(right[a].items())],
                "contexts": contexts,
            }
            # Normalize tables to kernel format: list of rows; each row is list of [state, sym, next]
            # Actually kernel expects left[i][x] as state or null. We'll emit as list of dicts? 
            # The spec says left[i][x] is the state reached from i on x, or null.
            # So left is a list (indexed by state) of dicts? It says "left[i][x]".
            # We'll emit as list of lists: left[i] is a list of length 2? Or dict.
            # The kernel in the problem statement uses left[i][x]; likely a list of dicts.
            # We'll emit list of dicts.
            cert["left"] = [dict(row) for row in left]
            cert["right"] = [dict(row) for row in right]
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None