import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _trans(table, n_states, n_symbols):
    t = table
    return t


def _dfa_canonical(n_states, n_symbols):
    # BFS-canonical enumeration of DFAs with states 0..n-1, state 0 loops on symbol 0.
    # Represent a DFA as a tuple of length n_states of tuples of length n_symbols.
    # State 0 must satisfy d[0][0] == 0.
    # We enumerate all target assignments consistent with canonical BFS order:
    # state i (i>0) must be reachable from 0.
    # For simplicity we enumerate all tables where transitions of state 0 are only to
    # already-"named" states in BFS order: BFS order names states 0, then 1,2,...
    # when first reached. So state i (i>0) has its first appearance at some parent.
    # We do a simple recursive enumeration: build d state by state; when choosing
    # d[i][x] for the first time, allowed targets are 0..current_max (already named)
    # plus one new state (which becomes current_max+1), but only if that new state is
    # actually needed; to keep it simple we allow any target 0..n_states-1 as long as
    # the resulting table is reachable from 0 and state 0 loops on 0.
    seen = set()
    out = []
    n = n_states

    def rec(i, d):
        if i == n:
            # check reachability
            reach = [False] * n
            reach[0] = True
            stack = [0]
            while stack:
                u = stack.pop()
                for x in range(n_symbols):
                    v = d[u][x]
                    if not reach[v]:
                        reach[v] = True
                        stack.append(v)
            if not all(reach):
                return
            t = tuple(tuple(row) for row in d)
            if t not in seen:
                seen.add(t)
                out.append(t)
            return
        # choose row i
        if i == 0:
            # state 0 must loop on symbol 0
            for x1 in range(n):
                d[0] = (0,) + tuple(0 for _ in range(n_symbols - 1))
                # fill x1..x_{n-1} in order
                def rec0(x, row):
                    if x == n_symbols:
                        d[0] = row
                        rec(1, d)
                        return
                    for v in range(n):
                        rec0(x + 1, row + (v,))
                rec0(1, (0,))
        else:
            # for states > 0, all targets allowed
            for v in range(n):
                d[i] = (v,)
                # fill remaining symbols
                def reci(x, row):
                    if x == n_symbols:
                        rec(i + 1, d)
                        return
                    for vv in range(n):
                        reci(x + 1, row + (vv,))
                reci(1, (v,))

    d = [None] * n
    rec(0, d)
    return out


def _far_to_head_from_rev_nfa(n_states, n_symbols, nfa):
    # nfa: list of (states, symbols, transitions) for an NFA reading head-to-far.
    # We want a DFA reading far-to-head whose language is the reverse of the NFA's
    # language.  Reverse-determinize: reverse the NFA (swap start/final), determinize
    # with subset construction, then reverse the resulting DFA (swap start/final and
    # reverse every transition), then determinize again.
    # For our purposes the half-tape alphabet is {0,1}.
    # nfa format: (n_states, n_symbols, start, finals, delta) where delta is list of
    # dicts: for state u and symbol x, delta[u][x] = set of v.
    ns, nsm, start, finals, delta = nfa
    # reverse NFA: final states become starts, transitions reversed
    rev_delta = [dict() for _ in range(ns)]
    for u in range(ns):
        for x in range(nsm):
            for v in delta[u].get(x, ()):
                rev_delta[v].setdefault(x, set()).add(u)
    # determinize rev NFA (subset construction)
    subsets = {}
    start_set = frozenset(finals)
    subsets[start_set] = 0
    order = [start_set]
    dfa_delta = []
    dfa_finals = set()
    i = 0
    while i < len(order):
        S = order[i]
        row = {}
        for x in range(nsm):
            T = set()
            for u in S:
                for v in rev_delta[u].get(x, ()):
                    T.add(v)
            T = frozenset(T)
            if T not in subsets:
                subsets[T] = len(order)
                order.append(T)
            row[x] = subsets[T]
        if 0 in S:
            dfa_finals.add(i)
        dfa_delta.append(row)
        i += 1
    # now reverse this DFA: swap start/final, reverse transitions
    # determinize the reversed NFA (the DFA becomes an NFA with single transitions)
    nd = len(order)
    # build new NFA: states 0..nd-1, transitions reversed
    new_delta = [dict() for _ in range(nd)]
    for u in range(nd):
        for x in range(nsm):
            v = dfa_delta[u][x]
            new_delta[v].setdefault(x, set()).add(u)
    new_finals = {0}
    # determinize new NFA
    subsets2 = {}
    start_set2 = frozenset([u for u in range(nd) if u in new_finals])
    # start states of the reversed NFA are the old finals
    start_set2 = frozenset(dfa_finals)
    subsets2[start_set2] = 0
    order2 = [start_set2]
    dfa2_delta = []
    dfa2_finals = set()
    i = 0
    while i < len(order2):
        S = order2[i]
        row = {}
        for x in range(nsm):
            T = set()
            for u in S:
                for v in new_delta[u].get(x, ()):
                    T.add(v)
            T = frozenset(T)
            if T not in subsets2:
                subsets2[T] = len(order2)
                order2.append(T)
            row[x] = subsets2[T]
        if 0 in S:
            dfa2_finals.add(i)
        dfa2_delta.append(row)
        i += 1
    # convert to table: state -> list of targets, index by symbol
    table = []
    for u in range(len(order2)):
        row = []
        for x in range(nsm):
            row.append(dfa2_delta[u][x])
        table.append(row)
    return table, len(order2)


def _closure_contexts(table, n_states, n_symbols, left_table, right_table):
    # closed-context fixpoint.
    # contexts: set of (l, q, s, r)
    # q in 0..n_states-1, s in 0..n_symbols-1, l and r are automaton states
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        new = set()
        for (l, q, s, r) in list(contexts):
            key = (q, s)
            if key not in table:
                return None  # halting context
            w, move, q2 = table[key]
            if move == 1:
                if w not in (0, 1):
                    return None
                l2 = left_table[l][w] if left_table[l][w] is not None else None
                if l2 is None:
                    return None
                for (r2, s2) in _pairs_right(right_table, r):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in contexts:
                        contexts.add(ctx)
                        new.add(ctx)
                        changed = True
            else:
                if w not in (0, 1):
                    return None
                r2 = right_table[r][w] if right_table[r][w] is not None else None
                if r2 is None:
                    return None
                for (l2, s2) in _pairs_left(left_table, l):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in contexts:
                        contexts.add(ctx)
                        new.add(ctx)
                        changed = True
    if len(contexts) > 200000:
        return None
    return contexts


def _pairs_right(right_table, r):
    # all pairs (r2, s2) with right[r2][s2] == r and right[r2][s2] is not None
    out = []
    for r2 in range(len(right_table)):
        row = right_table[r2]
        for s2 in range(len(row)):
            if row[s2] is not None and row[s2] == r:
                out.append((r2, s2))
    return out


def _pairs_left(left_table, l):
    out = []
    for l2 in range(len(left_table)):
        row = left_table[l2]
        for s2 in range(len(row)):
            if row[s2] is not None and row[s2] == l:
                out.append((l2, s2))
    return out


def _make_cps_contexts(contexts):
    # convert context set to kernel format
    left = []
    right = []
    # rebuild automata from contexts: for a right move, l2 = left[l][w];
    # we need full tables.  Instead, we keep the automata we built.
    return contexts


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    # enumerate small DFAs for the left half-tape
    # We use a simple 1-state and 2-state DFA first: the last-n-cells automaton.
    # 1-state automaton: state 0 loops on 0 and 1 (memoryless).
    # 2-state automaton: remember last cell.
    # Try the 1-state automaton first.
    for n_auto in (1, 2, 3):
        for left_table in _dfa_canonical(n_auto, 2):
            # build right automaton as complement-ish: last-cell memory
            # For a real attempt we need the right side too.  Here we build the
            # right automaton as the mirror of the left one (last-cell memory).
            right_table = [list(row) for row in left_table]
            for r in range(n_auto):
                for x in range(2):
                    if right_table[r][x] is None:
                        right_table[r][x] = 0
            # now run the fixpoint
            contexts = _closure_contexts(table, n_states, 2, left_table, right_table)
            if contexts is None:
                continue
            if len(contexts) > 200000:
                continue
            # build certificate
            cert = {
                "kind": "cps",
                "left": [list(row) for row in left_table],
                "right": [list(row) for row in right_table],
                "contexts": sorted(contexts),
            }
            try:
                from neverhalt.kernel import check
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None


# The above is a skeleton; the real work is in the search helpers below.
# We keep the module self-contained and only use the standard library plus
# neverhalt, as required.


def _enumerate_dfa_transitions(n_states, n_symbols, max_states, budget):
    # enumerate every transition table with n_states rows, targets in 0..max_states-1,
    # state 0 loops on symbol 0, up to budget tables.
    # We generate lazily via an iterator.
    def gen(i, cur):
        if budget[0] <= 0:
            return
        if i == n_states:
            yield tuple(tuple(r) for r in cur)
            return
        if i == 0:
            for x1 in range(max_states):
                cur[0] = (0,) + tuple(0 for _ in range(n_symbols - 1))
                def rec0(x, row):
                    if budget[0] <= 0:
                        return
                    if x == n_symbols:
                        for t in gen(1, cur):
                            budget[0] -= 1
                            yield t
                        return
                    for v in range(max_states):
                        cur[0] = row + (v,)
                        yield from rec0(x + 1, row + (v,))
                yield from rec0(1, (0,))
        else:
            for v in range(max_states):
                cur[i] = (v,)
                def reci(x, row):
                    if budget[0] <= 0:
                        return
                    if x == n_symbols:
                        for t in gen(i + 1, cur):
                            budget[0] -= 1
                            yield t
                        return
                    for vv in range(max_states):
                        cur[i] = row + (vv,)
                        yield from reci(x + 1, row + (vv,))
                yield from reci(1, (v,))
    budget = [budget]
    cur = [None] * n_states
    yield from gen(0, cur)


def decide(tm):
    from neverhalt.tm import parse
    from neverhalt.kernel import check, Reject
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    # Try memoryless automaton (1 state) and last-cell (2 states) for both sides.
    for n_auto in (1, 2, 3):
        budget = [200000]
        for left_table in _enumerate_dfa_transitions(n_auto, 2, n_auto, 200000):
            # right automaton: use the same table (search over both sides is huge,
            # so start with symmetric memory).
            right_table = [list(row) for row in left_table]
            try:
                contexts = _closure_contexts(table, n_states, 2, left_table, right_table)
            except Exception:
                continue
            if contexts is None:
                continue
            if len(contexts) > 200000:
                continue
            cert = {
                "kind": "cps",
                "left": [list(row) for row in left_table],
                "right": [list(row) for row in right_table],
                "contexts": [list(c) for c in contexts],
            }
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None


# Final entry point expected by the harness.
NAME = "search-cps" if False else "search_cps" if False else "search-cps"


def decide(tm):
    # full decider: enumerate automata, build contexts, verify, return first.
    from neverhalt.tm import parse
    from neverhalt.kernel import check, Reject
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    for n_auto in (1, 2, 3, 4):
        for left_table in _enumerate_dfa_transitions(n_auto, 2, n_auto, 300000):
            # right automaton: mirror of left (same table) is a reasonable start.
            # A more general search would enumerate right tables too, but the
            # budget is limited; we keep the symmetric case.
            right_table = [list(row) for row in left_table]
            try:
                contexts = _closure_contexts(table, n_states, 2, left_table, right_table)
            except Exception:
                continue
            if contexts is None:
                continue
            if len(contexts) > 200000:
                continue
            cert = {
                "kind": "cps",
                "left": [list(row) for row in left_table],
                "right": [list(row) for row in right_table],
                "contexts": [list(c) for c in contexts],
            }
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None
