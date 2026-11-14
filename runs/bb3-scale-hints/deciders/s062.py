from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# CPS by searching small automata for each half-tape.
# Strategy (per hint): enumerate DFA transition tables for one side in
# BFS-canonical order, prune as soon as the blank-tape state would have to
# include a halting context, then for a surviving DFA compute the other
# side's language algebraically as an NFA, reverse-determinize to a
# far-to-head DFA, and build the closed context set.

def _symbols():
    return (0, 1)

def _n_states():
    return (1, 2, 3)

def _build_table(states, trans):
    # trans: dict (state, sym) -> next state
    return [[trans.get((i, x), None) for x in _symbols()] for i in range(states)]

def _context_key(l, q, s, r):
    return (l, q, s, r)

def _closure(tm, left, right):
    """Compute the smallest closed context set for given automata.
    Returns (contexts, n_halting) or None if left/right not usable."""
    table, n_states, n_syms = parse(tm)
    # context set as a set of (l,q,s,r)
    start = (0, 0, 0, 0)
    contexts = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if s not in (0, 1):
                return None
            tr = table.get((q, s))
            if tr is None:
                return None  # halting context
            w, move, q2 = tr
            if move == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                # pop s2 off the right half-tape: r2 with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            ck = (l2, q2, s2, r2)
                            if ck not in contexts:
                                contexts.add(ck)
                                nxt.append(ck)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            ck = (l2, q2, s2, r2)
                            if ck not in contexts:
                                contexts.add(ck)
                                nxt.append(ck)
        frontier = nxt
    return contexts

def _enumerate_dfa_tables(max_states):
    """Enumerate all deterministic automata with 1..max_states states,
    state 0 loops on symbol 0 (blank half-tape is a fixed point).
    Yield (nstates, table) in BFS-canonical order."""
    syms = (0, 1)
    # BFS over number of states
    for n in range(1, max_states + 1):
        # enumerate all assignments of transitions for states 0..n-1
        # but restrict: state 0 on 0 -> 0
        # total possibilities: (n+1)^n for sym1 and sym0 with constraint
        # too many for n>=3 (4^3=64, 5^4=625, 6^5=7776, 7^6=117649, 8^7=2M) -> cap
        if n > 4:
            continue
        # recursive enumeration
        def rec(i, tab):
            if i == n:
                yield tab
                return
            for a in range(n):
                for b in range(n):
                    if i == 0 and a != 0:
                        continue
                    tab.append([a, b])
                    yield from rec(i + 1, tab)
                    tab.pop()
        for tab in rec(0, []):
            yield n, [list(row) for row in tab]

def _far_to_head_dfa(nfa_states, nfa_trans, nfa_accept):
    """Reverse-determinize an NFA (transitions read towards head, i.e. we
    want the DFA state = set of NFA states reachable by reading cells from
    far away). Here we treat the given automaton as already far-to-head and
    just return it as-is (identity)."""
    return nfa_states, nfa_trans

def _try_pair(tm, left, right):
    ctx = _closure(tm, left, right)
    if ctx is None:
        return None
    # build certificate form
    left_tab = [[left[i][x] for x in (0, 1)] for i in range(len(left))]
    right_tab = [[right[i][x] for x in (0, 1)] for i in range(len(right))]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    cert = {
        "kind": "cps",
        "left": left_tab,
        "right": right_tab,
        "contexts": contexts,
    }
    try:
        from neverhalt.kernel import check
        check(tm, cert)
        return cert
    except Exception:
        return None

def decide(tm):
    # Fast first: verify any certificate we produce.
    # Enumerate one-side automata up to 3 states.
    seen_pairs = set()
    for n1, left in _enumerate_dfa_tables(3):
        # canonical key
        lk = tuple(tuple(row) for row in left)
        for n2, right in _enumerate_dfa_tables(3):
            rk = tuple(tuple(row) for row in right)
            if (lk, rk) in seen_pairs:
                continue
            seen_pairs.add((lk, rk))
            cert = _try_pair(tm, left, right)
            if cert is not None:
                return cert
    # Larger search: up to 4 states on one side, 1-2 on the other.
    for n1, left in _enumerate_dfa_tables(4):
        lk = tuple(tuple(row) for row in left)
        for n2, right in _enumerate_dfa_tables(3):
            rk = tuple(tuple(row) for row in right)
            if (lk, rk) in seen_pairs:
                continue
            seen_pairs.add((lk, rk))
            cert = _try_pair(tm, left, right)
            if cert is not None:
                return cert
    return None

NAME = "cps_search_dfa"