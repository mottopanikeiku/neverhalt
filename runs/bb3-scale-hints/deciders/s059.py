import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import Reject

sys.setrecursionlimit(1000000)


def _states_of(tm):
    t, ns, nsym = parse(tm)
    return ns


def _pair_of_halting_transitions(tm):
    t, ns, nsym = parse(tm)
    return t


def _transitions(tm):
    t, ns, nsym = parse(tm)
    out = {}
    for q in range(ns):
        for s in range(nsym):
            if (q, s) in t:
                w, mv, q2 = t[(q, s)]
                out[(q, s)] = (w, mv, q2)
    return out


def _empty_table(n_states, n_symbols):
    return [None] * (n_states * n_symbols)


def _read(table, n_states, n_symbols, st, sym):
    return table[st * n_symbols + sym]


def _write(table, n_states, n_symbols, st, sym, val):
    table[st * n_symbols + sym] = val


def _table_equal(a, b):
    return a == b


def _closure_left(tm, trans, left_table, n_left, n_symbols, n_contexts):
    # returns (contexts, ok) ; contexts as set of (l, q, s, r) but we only need left part
    # We will implement full pair closure in the main function.
    return None


def _enumerate_dfa_tables(n_states, n_symbols, prefix=None, budget=None, max_states=3):
    """Yield all transition tables of n_states states over n_symbols alphabet
    with state 0 looping on symbol 0 (blank), remaining entries either None or
    a state in [0, n_states) (target).  We only enumerate target choices for
    non-None entries: for states > 0 all symbols are non-blank? No: a DFA reads
    cells; each read may be 0 or 1.  So every entry is either None or a state.
    Enumerate over (target or None) for each (state, symbol) except (0,0)->0."""
    if prefix is None:
        prefix = [None] * (n_states * n_symbols)
    _write(prefix, n_states, n_symbols, 0, 0, 0)
    if budget is not None:
        budget[0] -= 1
        if budget[0] < 0:
            return
    idx = 1
    total = n_states * n_symbols
    while idx < total:
        st = idx // n_symbols
        sym = idx % n_symbols
        if st == 0 and sym == 0:
            idx += 1
            continue
        chosen = [None]
        for tgt in range(n_states):
            chosen.append(tgt)
        for c in chosen:
            _write(prefix, n_states, n_symbols, st, sym, c)
            yield prefix[:]
        idx += 1


def _enumerate_all_dfa_tables(max_states, n_symbols, budget=None):
    for n_states in range(1, max_states + 1):
        for tab in _enumerate_dfa_tables(n_states, n_symbols, budget=budget):
            yield n_states, tab


def _handle_move_right(tm, trans, ns, n_symbols, l, q, s, r, right_table, n_right,
                       context_set):
    # (q, s) -> (w, mv, q2); mv = +1 means right
    if (q, s) not in trans:
        return False
    w, mv, q2 = trans[(q, s)]
    if mv != 1:
        return None
    wl = w  # symbol written under head is pushed to left half-tape
    lv = _read(right_table, n_right, n_symbols, r, s)
    if lv is None:
        return False
    # we need for EVERY (r2, s2) with right[r2][s2] == r a context
    # (l2, q2, s2, r2) where l2 = left[l][w]
    l2 = left_table[l * n_symbols + wl]
    if l2 is None:
        return False
    # find all (r2, s2) pairs mapping to r in right table
    pairs = []
    for r2 in range(n_right):
        for s2 in range(n_symbols):
            if _read(right_table, n_right, n_symbols, r2, s2) == r:
                pairs.append((r2, s2))
    for (r2, s2) in pairs:
        key = (l2, q2, s2, r2)
        if key not in context_set:
            context_set.add(key)
    return True


def _handle_move_left(tm, trans, ns, n_symbols, l, q, s, r, left_table, n_left,
                      context_set):
    if (q, s) not in trans:
        return False
    w, mv, q2 = trans[(q, s)]
    if mv != -1:
        return None
    rv = _read(left_table, n_left, n_symbols, l, w)
    if rv is None:
        return False
    # for every (l2, s2) with left[l2][s2] == l, context (l2, q2, s2, r)
    pairs = []
    for l2 in range(n_left):
        for s2 in range(n_symbols):
            if _read(left_table, n_left, n_symbols, l2, s2) == l:
                pairs.append((l2, s2))
    for (l2, s2) in pairs:
        key = (l2, q2, s2, r)
        if key not in context_set:
            context_set.add(key)
    return True


def _closure(tm, trans, ns, n_symbols, left_table, n_left, right_table, n_right,
             budget):
    context_set = set()
    context_set.add((0, 0, 0, 0))
    stack = [(0, 0, 0, 0)]
    ok = True
    while stack:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        (l, q, s, r) = stack.pop()
        if (q, s) not in trans:
            ok = False
            return None
        w, mv, q2 = trans[(q, s)]
        if mv == 1:
            l2 = _read(left_table, n_left, n_symbols, l, w)
            if l2 is None:
                ok = False
                return None
            seen_any = False
            for r2 in range(n_right):
                for s2 in range(n_symbols):
                    if _read(right_table, n_right, n_symbols, r2, s2) == r:
                        seen_any = True
                        key = (l2, q2, s2, r2)
                        if key not in context_set:
                            context_set.add(key)
                            stack.append(key)
            if not seen_any:
                # r has no predecessors in right automaton; that is fine as long
                # as we never need to pop.  But if no pair exists, the context is
                # still valid (nothing to cover).
                pass
        else:
            r2 = _read(right_table, n_right, n_symbols, r, w)
            if r2 is None:
                ok = False
                return None
            seen_any = False
            for l2 in range(n_left):
                for s2 in range(n_symbols):
                    if _read(left_table, n_left, n_symbols, l2, s2) == l:
                        seen_any = True
                        key = (l2, q2, s2, r2)
                        if key not in context_set:
                            context_set.add(key)
                            stack.append(key)
            if not seen_any:
                pass
    return context_set


def _is_closed(tm, trans, ns, n_symbols, left_table, n_left, right_table, n_right,
               context_set, budget):
    # verify each context satisfies the kernel rule
    for (l, q, s, r) in context_set:
        if (q, s) not in trans:
            return False
        w, mv, q2 = trans[(q, s)]
        if mv == 1:
            l2 = _read(left_table, n_left, n_symbols, l, w)
            if l2 is None:
                return False
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(n_right):
                for s2 in range(n_symbols):
                    if _read(right_table, n_right, n_symbols, r2, s2) == r:
                        if (l2, q2, s2, r2) not in context_set:
                            return False
        else:
            r2 = _read(right_table, n_right, n_symbols, r, w)
            if r2 is None:
                return False
            for l2 in range(n_left):
                for s2 in range(n_symbols):
                    if _read(left_table, n_left, n_symbols, l2, s2) == l:
                        if (l2, q2, s2, r2) not in context_set:
                            return False
    return True


def decide(tm: str):
    budget = [4000000]
    try:
        t, ns, nsym = parse(tm)
    except Exception:
        return None
    trans = {}
    for q in range(ns):
        for s in range(nsym):
            if (q, s) in t:
                w, mv, q2 = t[(q, s)]
                trans[(q, s)] = (w, mv, q2)
    # quick run
    try:
        halted, steps, st, pos, tape = run(tm, 200)
        if halted:
            return None
    except Exception:
        return None

    n_symbols = nsym
    # enumerate DFAs for the left half-tape, small first
    results = []
    for left_n in range(1, 4):
        for left_tab in _enumerate_dfa_tables(left_n, n_symbols, budget=budget):
            # left_tab is a list of length left_n*n_symbols
            # try to find a right table by closure: we build right table as the
            # set of states reachable in the closure of (0,0,0,0); instead we
            # enumerate right tables too but with a small bound on the number
            # of contexts, using a fixpoint.
            # Simpler: enumerate right tables of the same size and run closure.
            for right_n in range(1, 4):
                for right_tab in _enumerate_dfa_tables(right_n, n_symbols, budget=budget):
                    budget[0] -= 1
                    if budget[0] < 0:
                        return None
                    # state 0 loops on symbol 0 already
                    # closure
                    ctx = _closure(tm, trans, ns, n_symbols,
                                   left_tab, left_n, right_tab, right_n, budget)
                    if ctx is None:
                        continue
                    if len(ctx) > 200000:
                        continue
                    if _is_closed(tm, trans, ns, n_symbols, left_tab, left_n,
                                  right_tab, right_n, ctx, budget):
                        # build certificate
                        left = []
                        for i in range(left_n):
                            row = []
                            for x in range(n_symbols):
                                v = _read(left_tab, left_n, n_symbols, i, x)
                                row.append(v)
                            left.append(row)
                        right = []
                        for i in range(right_n):
                            row = []
                            for x in range(n_symbols):
                                v = _read(right_tab, right_n, n_symbols, i, x)
                                row.append(v)
                            right.append(row)
                        contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                        return {"kind": "cps", "left": left, "right": right,
                                "contexts": contexts}
    return None