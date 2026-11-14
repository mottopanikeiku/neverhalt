import sys
from collections import deque
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(100000)


def _norm_table(tab, n):
    # BFS-canonical form of a partial DFA table: states 0..n-1, transitions 0/1 or None.
    # Canonicalize by first-visit order from state 0.
    seen = {0: 0}
    order = [0]
    q = deque([0])
    while q:
        s = q.popleft()
        for x in (0, 1):
            t = tab.get((s, x))
            if t is None:
                continue
            if t not in seen:
                seen[t] = len(order)
                order.append(t)
                q.append(t)
    mp = {old: new for new, old in enumerate(order)}
    out = {}
    for old, new in mp.items():
        for x in (0, 1):
            t = tab.get((old, x))
            if t is not None:
                out[(new, x)] = mp[t]
    return out, len(order)


class DFA:
    __slots__ = ("n", "tab")

    def __init__(self, n, tab):
        self.n = n
        self.tab = tab  # (state, symbol) -> state or None


def _complete_transitions(dfa):
    """List of all (state, symbol) pairs that are defined (in BFS order)."""
    res = []
    for s in range(dfa.n):
        for x in (0, 1):
            if (s, x) in dfa.tab:
                res.append((s, x))
    return res


def _build_cps_contexts(tm, table, n_states, n_symbols, left_dfa, right_dfa):
    """Closed-context fixpoint. Returns (contexts, ok) or (None, False)."""
    # contexts: set of (l, q, s, r)
    start = (0, 0, 0, 0)
    ctx = {start}
    frontier = deque([start])
    # Precompute reverse transitions of right DFA: right[r2][s2] == r
    right_rev = {}
    for (r2, s2), r in right_dfa.tab.items():
        right_rev.setdefault(r, []).append((r2, s2))
    left_rev = {}
    for (l2, s2), l in left_dfa.tab.items():
        left_rev.setdefault(l, []).append((l2, s2))

    while frontier:
        l, q, s, r = frontier.popleft()
        tr = table.get((q, s))
        if tr is None:
            return None, False  # halting context
        w, move, q2 = tr
        if move == 1:
            # step right: l2 = left[l][w]
            l2 = left_dfa.tab.get((l, w))
            if l2 is None:
                return None, False
            for (r2, s2) in right_rev.get(r, ()):
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    ctx.add(c)
                    frontier.append(c)
        else:
            r2 = right_dfa.tab.get((r, w))
            if r2 is None:
                return None, False
            for (l2, s2) in left_rev.get(l, ()):
                c = (l2, q2, s2, r2)
                if c not in ctx:
                    ctx.add(c)
                    frontier.append(c)
    return ctx, True


def _emit(tm, left_dfa, right_dfa):
    table, n_states, n_symbols = parse(tm)
    ctx, ok = _build_cps_contexts(tm, table, n_states, n_symbols, left_dfa, right_dfa)
    if not ok:
        return None
    left_tab = [[None, None] for _ in range(left_dfa.n)]
    for (s, x), t in left_dfa.tab.items():
        left_tab[s][x] = t
    right_tab = [[None, None] for _ in range(right_dfa.n)]
    for (s, x), t in right_dfa.tab.items():
        right_tab[s][x] = t
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    return {"kind": "cps", "left": left_tab, "right": right_tab, "contexts": contexts}


def _enumerate_dfa(n_states, maxlen):
    """Yield DFAs with n_states states, state 0 loops on 0, BFS-canonical, size <= maxlen.
    Tab is a dict (state, symbol) -> state (total transitions only). We enumerate
    partial DFAs by adding transitions one at a time in a canonical order."""
    # Represent DFA as tuple of transitions for (s,x) in fixed order, value None or target.
    pairs = [(s, x) for s in range(n_states) for x in (0, 1)]
    # State 0 must loop on 0 (blank tape maps to blank).
    # Enumerate assignments in BFS-canonical order: state ids are assigned on first
    # reachability from 0 via defined transitions. To keep it simple we enumerate
    # all partial transition functions with targets < n_states, then canonicalize
    # and dedupe, keeping only those where 0 is the start and reachable states are
    # numbered in first-visit order.
    seen = set()
    total = len(pairs)
    # DFS over pairs
    def rec(i, acc):
        if i == total:
            # canonicalize: renumber reachable states from 0
            tab = dict(acc)
            # reachability
            seen_s = {0}
            dq = deque([0])
            order = [0]
            while dq:
                s = dq.popleft()
                for x in (0, 1):
                    t = tab.get((s, x))
                    if t is not None and t not in seen_s:
                        seen_s.add(t)
                        order.append(t)
                        dq.append(t)
            if len(order) > n_states:
                return
            mp = {old: new for new, old in enumerate(order)}
            nt = {}
            for (s, x), t in tab.items():
                if t is not None:
                    nt[(mp[s], x)] = mp[t]
            key = tuple(sorted(nt.items()))
            if key in seen:
                return
            seen.add(key)
            yield DFA(len(order), nt)
            return
        s, x = pairs[i]
        # option: undefined
        yield from rec(i + 1, acc)
        for t in range(n_states):
            acc[(s, x)] = t
            yield from rec(i + 1, acc)
            del acc[(s, x)]
    yield from rec(0, {})


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Try all pairs of DFAs up to 4 states each, in increasing total size.
    dfas = []
    for n in (1, 2, 3, 4):
        for dfa in _enumerate_dfa(n, 0):
            dfas.append(dfa)
    # Limit work: iterate pairs by sum of states.
    dfas.sort(key=lambda d: d.n)
    for ld in dfas:
        for rd in dfas:
            if ld.n + rd.n > 8:
                continue
            cert = _emit(tm, ld, rd)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))
