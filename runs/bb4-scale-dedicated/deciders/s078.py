from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _table(tm):
    tab, ns, _ = parse(tm)
    return tab, ns


def _sig(t):
    return tuple(t)


def _canon(t):
    """BFS-canonical representative of the partial DFA state set (states 0..n-1)."""
    n = len(t)
    seen = {0: 0}
    order = [0]
    q = 0
    while q < len(order):
        cur = order[q]
        q += 1
        for x in (0, 1):
            sym = t[cur][x]
            if sym is None:
                continue
            if sym not in seen:
                seen[sym] = len(order)
                order.append(sym)
    if len(order) != n:
        return None
    return tuple(order)


def _backward_states(tab, ns):
    """States that can reach a halting transition (no transition) at all."""
    bad = set()
    changed = True
    while changed:
        changed = False
        for q in range(ns):
            for x in (0, 1):
                if (q, x) not in tab:
                    if q not in bad:
                        bad.add(q)
                        changed = True
    # propagate backwards
    changed = True
    while changed:
        changed = False
        for q in range(ns):
            for x in (0, 1):
                e = tab.get((q, x))
                if e is None:
                    continue
                w, mv, q2 = e
                if q2 in bad and q not in bad:
                    bad.add(q)
                    changed = True
    return bad


def _enumerate_tables(n, max_tables=20000):
    """Enumerate all partial DFA tables on n states with state 0 looping on 0.
    Returns them in order of increasing number of non-null transitions, which
    tends to put small languages first. Representative per canonical form."""
    out = []
    seen = set()
    total = 2 * (n - 1) + 1
    for mask in range((1 << total) - 1, -1, -1):
        t = [None] * n
        t[0] = [0, None]
        bits = mask
        for i in range(1, n):
            for x in (0, 1):
                if bits & 1:
                    bits >>= 1
                    t[i][x] = i
        # mask only sets self loops; we additionally allow transitions to any state
        # by a second enumeration below
    # The above is too coarse; do a proper enumeration of all functions.
    # Represent each of the 2n entries as -1 (null) or a state in [0,n).
    entries = 2 * n
    alphabet_size = 1 + n
    limit = n ** 0
    # enumerate all tables with at most 8 non-null entries to keep it tractable
    import itertools
    states = list(range(1, n)) + [0]
    for k in range(entries + 1):
        if k > 10:
            break
        for combo in itertools.combinations(range(entries), k):
            t = [[None, None] for _ in range(n)]
            t[0][0] = 0
            ok = True
            for idx in combo:
                si, x = divmod(idx, 2)
                t[si][x] = states[idx % n]
            key = tuple(tuple(r) for r in t)
            if key in seen:
                continue
            seen.add(key)
            c = _canon([tuple(r) for r in t])
            if c is None:
                continue
            out.append(t)
            if len(out) >= max_tables:
                return out
    return out


def _close_contexts(tab, ns, left, right):
    """Run the closed-context fixpoint.  Returns the context set or None."""
    # context = (l, q, s, r)
    # left is a list of rows; left[i][x] -> j or None
    # right likewise
    # Start with the empty language: all contexts reachable from (0,0,0,0)
    # We build the set by BFS from the initial context.  Then check closure:
    # every context must have all its successors present.
    from collections import deque
    seen = set()
    dq = deque()
    seen.add((0, 0, 0, 0))
    dq.append((0, 0, 0, 0))
    while dq:
        l, q, s, r = dq.popleft()
        e = tab.get((q, s))
        if e is None:
            return None
        w, mv, q2 = e
        # left automaton consumes w: l2 = left[l][w]
        l2 = None
        for x in (0, 1):
            if left[l][x] == w:
                l2 = x
                break
        if l2 is None:
            return None
        if mv == +1:
            # right move: for every (r2, s2) with right[r2][s2] == r, add (l2, q2, s2, r2)
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in seen:
                            seen.add(nxt)
                            dq.append(nxt)
        else:
            # left move: for every (l2b, s2) with left[l2b][s2] == l
            for l2b in range(len(left)):
                for s2 in (0, 1):
                    if left[l2b][s2] == l:
                        nxt = (l2, q2, s2, l2b)
                        if nxt not in seen:
                            seen.add(nxt)
                            dq.append(nxt)
    return seen


def decide(tm):
    tab, ns = _table(tm)
    # quick cycle attempt with a short simulation
    try:
        from neverhalt.tm import run as _run
        for T in range(0, 200, 10):
            for P in range(1, 120):
                h, steps, st, pos, tape = _run(tm, T + P)
                if h:
                    continue
                h2, _, st2, pos2, tape2 = _run(tm, T)
                if st == st2 and pos2 - pos == 0:
                    # plain cycle check
                    try:
                        cert = {"kind": "cycle", "t": T, "p": P}
                        from neverhalt.kernel import check as _ch
                        _ch(tm, cert)
                        return cert
                    except Exception:
                        pass
    except Exception:
        pass

    # Search half-tape DFAs
    for n in (1, 2, 3, 4):
        tables = _enumerate_tables(n, max_tables=3000)
        for t in tables:
            # left automaton = t; right automaton = t
            ctx = _close_contexts(tab, ns, t, t)
            if ctx is None:
                continue
            # emit
            try:
                left = [list(row) for row in t]
                right = [list(row) for row in t]
                contexts = [[a, b, c, d] for (a, b, c, d) in ctx]
                cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
                from neverhalt.kernel import check as _ch
                _ch(tm, cert)
                return cert
            except Exception:
                continue
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(decide(sys.argv[1]))
    else:
        # tiny self-test
        print("ok")
