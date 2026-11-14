import sys
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(1000000)


def _parse(tm):
    table, ns, nsym = parse(tm)
    return table, ns, nsym


def _determinize_pairs(tm):
    """Try to build a cps certificate by enumerating small half-tape automata.

    We enumerate candidate DFAs for one half-tape in BFS-canonical order with
    growing size (up to 10 states). For each candidate left automaton, we
    construct a right automaton by reverse-determinizing the same language
    (the half-tape read far-to-head is the reverse of head-to-far, so the
    reverse NFA is determinized). Then we run the closed-context fixpoint.
    """
    table, ns, nsym = _parse(tm)
    # state 0 is blank tape; symbols are 0 and 1 here
    states = list(range(ns))
    trans = []
    for (q, s), (w, mv, q2) in table.items():
        trans.append((q, s, w, mv, q2))

    # Precompute for each context whether it can lead to a halt by forward
    # simulation in the abstract domain: we simply enumerate all reachable
    # contexts from [0,0,0,0] for each automaton pair and check halting.
    results = []

    # Enumerate DFAs of size 1..10 over alphabet {0,1} with state 0 looping on 0.
    # BFS-canonical enumeration of transition tables.
    def enum_dfas(max_states):
        # Represent DFA as tuple (delta, n) where delta[i][x] in 0..n-1; state 0
        # must have delta[0][0] == 0.
        out = []
        for n in range(1, max_states + 1):
            # DFS over all tables with canonical BFS ordering: we generate all
            # tables and filter by BFS-canonical (state i+1 is reached before
            # state i+2, etc. in BFS from state 0).
            def rec(i, cur):
                if i == n:
                    # check canonical: BFS order
                    seen = {0}
                    frontier = [0]
                    order = [0]
                    while frontier:
                        nxt = []
                        for s in frontier:
                            for x in (0, 1):
                                t = cur[s][x]
                                if t not in seen:
                                    seen.add(t)
                                    nxt.append(t)
                        order.extend(nxt)
                        frontier = nxt
                    if len(order) != n:
                        return
                    # require order == list(range(n))
                    if order != list(range(n)):
                        return
                    # state 0 loops on 0
                    if cur[0][0] != 0:
                        return
                    out.append(tuple(tuple(cur[s]) for s in range(n)))
                    return
                for a in range(n):
                    for b in range(n):
                        cand = [list(x) for x in cur]
                        cand[i] = [a, b]
                        rec(i + 1, cand)
            rec(0, [[0, 0] for _ in range(n)])
        return out

    try:
        dfas = enum_dfas(10)
    except Exception:
        dfas = []

    # If enumeration is too large, fall back to a smaller set.
    if len(dfas) > 5000:
        dfas = dfas[:5000]

    # For each DFA, try to build the other side by reverse determinization.
    def reverse_determinize(dfa):
        n = len(dfa)
        # The reverse NFA has states 0..n-1; transitions reversed. Then
        # determinize by subset construction over the reversed language.
        # Start from the set of states that can reach state 0 in the original
        # DFA (i.e., states from which blank tape is reachable), because the
        # right half-tape read far-to-head is the reverse of head-to-far.
        # Build reverse graph.
        rev = [[] for _ in range(n)]
        for s in range(n):
            for x in (0, 1):
                rev[dfa[s][x]].append((s, x))
        # DFA for the reversed language: start at accepting set of reversed
        # NFA = states from which 0 is reachable.
        reach0 = [False] * n
        reach0[0] = True
        stack = [0]
        while stack:
            u = stack.pop()
            for (v, x) in rev[u]:
                if not reach0[v]:
                    reach0[v] = True
                    stack.append(v)
        start = frozenset(i for i in range(n) if reach0[i])
        # Determinize.
        delta = {}
        order = []
        q = start
        delta[q] = {}
        order.append(q)
        idx = 0
        while idx < len(order):
            cur = order[idx]
            idx += 1
            for x in (0, 1):
                nxt = frozenset(rev[v][1] for v in cur for rev_v in rev[v] if rev_v[1] == x)
                # recompute properly
                nxt = set()
                for v in cur:
                    for (u, xx) in rev[v]:
                        if xx == x:
                            nxt.add(u)
                nxt = frozenset(nxt)
                if nxt not in delta:
                    delta[nxt] = {}
                    order.append(nxt)
                delta[cur][x] = nxt
        # Map subsets to ints.
        mapping = {}
        for s in order:
            mapping[s] = len(mapping)
        trans = []
        for s in order:
            row = []
            for x in (0, 1):
                t = delta[s][x]
                row.append(mapping[t] if t in mapping else None)
            trans.append(row)
        # Normalize: state 0 must loop on 0.
        # Find the start state; if it loops on 0 that's fine, else add a new
        # state 0 that loops on 0 and jumps to the old start on 1.
        start_i = mapping[start]
        if trans[start_i][0] != start_i:
            newtrans = [[0, 0]]
            old = trans
            for row in old:
                newtrans.append([row[0], row[1]])
            newtrans.append([start_i, start_i])
            trans = newtrans
        return trans

    def closure(left, right):
        # left[i][x], right[i][x] are ints or None; state 0 loops on 0 for both.
        # Build transition table of the machine as (w, move, q2) or None (halt).
        T = {}
        for (q, s), (w, mv, q2) in table.items():
            T[(q, s)] = (w, mv, q2)
        # contexts: (l, q, s, r)
        start = (0, 0, 0, 0)
        seen = {start}
        stack = [start]
        ctx = set([start])
        while stack:
            (l, q, s, r) = stack.pop()
            tr = T.get((q, s))
            if tr is None:
                return None  # halting context found
            (w, mv, q2) = tr
            if mv == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in [(r, 0), (r, 1)]:
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in [(l, 0), (l, 1)]:
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
        if len(seen) > 200000:
            return None
        # Emit certificate.
        L = [[row[0], row[1]] for row in left]
        R = [[row[0], row[1]] for row in right]
        contexts = [[c[0], c[1], c[2], c[3]] for c in seen]
        cert = {"kind": "cps", "left": L, "right": R, "contexts": contexts}
        return cert

    for left in dfas:
        right = reverse_determinize(left)
        cert = closure(left, right)
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None


def decide(tm: str):
    try:
        return _determinize_pairs(tm)
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))
    else:
        print(decide("1RB1LB_1LA---"))
