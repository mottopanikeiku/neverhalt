import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _transitions(tm):
    table, n_states, n_symbols = parse(tm)
    n_sym = 2
    t = [[(None, None, None) for _ in range(n_sym)] for _ in range(n_states)]
    for q in range(n_states):
        for s in range(n_sym):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                t[q][s] = (int(w), 1 if mv > 0 else -1, q2)
    return t, n_states


def _dfa_canon(states, trans):
    start = 0
    seen = {start: 0}
    order = [start]
    i = 0
    while i < len(order):
        u = order[i]
        i += 1
        for x in (0, 1):
            v = trans[u][x]
            if v is None:
                continue
            if v not in seen:
                seen[v] = len(order)
                order.append(v)
    return len(order), [seen.get(u, -1) for u in range(states)]


def _enumerate_dfas(max_states, max_edges):
    """Yield (n, mapping) for DFAs with n states, state 0 = blank loop on 0."""
    for n in range(1, max_states + 1):
        # BFS-canonical enumeration of partial DFAs with state 0 looping on 0.
        # Represent each state's transitions as a pair (on 0, on 1), -1 = null.
        # Enumerate all tables where state 0 on 0 -> 0.
        import itertools
        # We enumerate by number of "real" transitions; keep it bounded.
        count = 0
        for bits in itertools.product(range(-1, n), repeat=2 * n):
            if count > max_edges:
                break
            count += 1
            if bits[0] != 0:
                continue
            # canonical check: state 0 must be the BFS root; require the
            # table already be canonical (states discovered in order).
            trans = [[bits[2 * u + x] for x in range(2)] for u in range(n)]
            # reachability from 0
            reach = [False] * n
            reach[0] = True
            stack = [0]
            while stack:
                u = stack.pop()
                for x in range(2):
                    v = trans[u][x]
                    if v is not None and not reach[v]:
                        reach[v] = True
                        stack.append(v)
            if not all(reach):
                continue
            # BFS-canonical: state ids follow BFS discovery order
            order = [0]
            seen = {0}
            qi = 0
            ok = True
            while qi < len(order):
                u = order[qi]
                qi += 1
                for x in range(2):
                    v = trans[u][x]
                    if v is not None and v not in seen:
                        seen.add(v)
                        order.append(v)
                    elif v is not None and seen[v] and order.index(v) > len(order) - 1:
                        pass
            # require ids to be exactly 0..n-1 in BFS order
            seq = []
            seen2 = {0}
            frontier = [0]
            while frontier:
                nxt = []
                for u in frontier:
                    for x in range(2):
                        v = trans[u][x]
                        if v is not None and v not in seen2:
                            seen2.add(v)
                            nxt.append(v)
                seq.extend(nxt)
                frontier = nxt
            if seq != list(range(1, n)):
                continue
            yield n, trans


def _build_cps(tm, left, right, t, n_states):
    """Fixpoint of contexts; return cert dict or None."""
    # context: (l, q, s, r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    changed = True
    while changed:
        changed = False
        for (l, q, s, r) in list(contexts):
            tr = t[q][s]
            if tr is None:
                return None
            w, mv, q2 = tr
            if mv > 0:
                l2 = left[l][w]
                if l2 is None:
                    return None
                # for every (r2, s2) with right[r2][s2] == r
                for r2 in range(len(right)):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for l2 in range(len(left)):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                changed = True
    if len(contexts) > 200000:
        return None
    return {
        "kind": "cps",
        "left": left,
        "right": right,
        "contexts": [list(c) for c in contexts],
    }


def decide(tm: str):
    t, n_states = _transitions(tm)
    # quick halt check
    try:
        halted, steps, state, pos, tape = run(tm, 300)
        if halted:
            return None
    except Exception:
        return None
    max_states = 7
    # enumerate left automata and right automata, interleave by growing size
    for nL in range(1, max_states + 1):
        for nR in range(1, max_states + 1):
            found = False
            for left_t in _enumerate_dfas(nL, 400):
                if found:
                    break
                for right_t in _enumerate_dfas(nR, 400):
                    cert = _build_cps(tm, left_t, right_t, t, n_states)
                    if cert is not None:
                        # verify against kernel
                        try:
                            check(tm, cert)
                            return cert
                        except Exception:
                            continue
                    if cert is not None:
                        found = True
            if found:
                break
        if found:
            break
    return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    if c:
        print("FOUND", c["kind"])
    else:
        print("none")
