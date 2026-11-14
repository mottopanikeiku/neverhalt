from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

def decide(tm: str):
    try:
        table, n_states, _ = parse(tm)
    except Exception:
        return None
    # transitions: dict (q,s) -> (w, move, q2); move +1 right, -1 left
    trans = {}
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
                trans[(q, s)] = (w, move, q2)

    # states of the two automata are pairs (base_state, symbol) reachable
    # from the blank tape, read far-to-head; state 0 = all blank.
    def build_auto(base_states, max_states):
        # deterministic automaton: state -> (next_state_on_0, next_state_on_1)
        # canonical BFS enumeration over tables with states 0..m-1, state 0
        # loops on 0 (blank half-tape stays blank).
        results = []
        for m in range(1, max_states + 1):
            # enumerate all tables for states 1..m-1 on symbols {0,1};
            # state 0 is fixed: on 0 -> 0, on 1 -> some state in 0..m-1
            # (on 1 it cannot stay blank conceptually, but allow it for search)
            n_free = m - 1
            total = m ** (2 * n_free + 1)
            for code in range(total):
                # decode
                a = [[0, 0] for _ in range(m)]
                a[0][0] = 0
                idx = 0
                # state 0 on 1
                a[0][1] = code % m
                code //= m
                for st in range(1, m):
                    a[st][0] = code % m
                    code //= m
                    a[st][1] = code % m
                    code //= m
                # prune: reachable set from 0 must be all states (canonical)
                # BFS reachability
                seen = {0}
                stack = [0]
                while stack:
                    u = stack.pop()
                    for x in (0, 1):
                        v = a[u][x]
                        if v not in seen:
                            seen.add(v)
                            stack.append(v)
                if len(seen) != m:
                    continue
                # canonical: smallest BFS order numbering must equal 0..m-1
                order = [0]
                seen2 = {0}
                while order:
                    u = order.pop(0)
                    for x in (0, 1):
                        v = a[u][x]
                        if v not in seen2:
                            seen2.add(v)
                            order.append(v)
                # renumber by order
                ren = {st: i for i, st in enumerate(order)}
                b = [[ren[a[u][x]] for x in (0, 1)] for u in range(m)]
                # check b is canonical: BFS order from 0 gives 0,1,2,...
                order2 = [0]
                seen3 = {0}
                while order2:
                    u = order2.pop(0)
                    for x in (0, 1):
                        v = b[u][x]
                        if v not in seen3:
                            seen3.add(v)
                            order2.append(v)
                if order2 != list(range(m)):
                    continue
                results.append(b)
            if results:
                yield from results
                # move to next size
            if len(results) > 200000:
                break
        # if nothing found up to max_states, yield nothing

    def closure(left, right, max_ctx=200000):
        # left: list of [next0,next1] per state; right likewise.
        # context (l, q, s, r)
        start = (0, 0, 0, 0)
        ctx = {start}
        frontier = [start]
        while frontier:
            newf = []
            for (l, q, s, r) in frontier:
                if (q, s) not in trans:
                    return None
                w, move, q2 = trans[(q, s)]
                if move > 0:
                    # write w on the left half-tape: l2 = left[l][w]
                    l2 = left[l][w]
                    if l2 is None:
                        return None
                    # pop s2 from the right: for every (r2, s2) with right[r2][s2]==r
                    for r2 in range(len(right)):
                        for s2 in (0, 1):
                            if right[r2][s2] == r:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    if len(ctx) >= max_ctx:
                                        return None
                                    ctx.add(c)
                                    newf.append(c)
                else:
                    r2 = right[r][w]
                    if r2 is None:
                        return None
                    for l2 in range(len(left)):
                        for s2 in (0, 1):
                            if left[l2][s2] == l:
                                c = (l2, q2, s2, r2)
                                if c not in ctx:
                                    if len(ctx) >= max_ctx:
                                        return None
                                    ctx.add(c)
                                    newf.append(c)
            frontier = newf
        return ctx

    def to_ctx_dict(ctx):
        contexts = []
        for (l, q, s, r) in sorted(ctx):
            contexts.append([l, q, s, r])
        return contexts

    # enumerate automata sizes 1..4 per side (state 0 loops on 0)
    autos = []
    import itertools
    for m in range(1, 5):
        found = []
        # enumerate tables for states 1..m-1; state 0 on 0 -> 0 fixed,
        # state 0 on 1 -> any state
        n_free = m - 1
        for code in range(m ** (2 * n_free + 1)):
            a = [[0, 0] for _ in range(m)]
            a[0][0] = 0
            idx = code
            a[0][1] = idx % m
            idx //= m
            ok = True
            for st in range(1, m):
                a[st][0] = idx % m
                idx //= m
                a[st][1] = idx % m
                idx //= m
            # reachability + canonical BFS
            seen = {0}
            stack = [0]
            while stack:
                u = stack.pop()
                for x in (0, 1):
                    v = a[u][x]
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            if len(seen) != m:
                continue
            order = [0]
            seen2 = {0}
            while order:
                u = order.pop(0)
                for x in (0, 1):
                    v = a[u][x]
                    if v not in seen2:
                        seen2.add(v)
                        order.append(v)
            ren = {st: i for i, st in enumerate(order)}
            b = [[ren[a[u][x]] for x in (0, 1)] for u in range(m)]
            order2 = [0]
            seen3 = {0}
            while order2:
                u = order2.pop(0)
                for x in (0, 1):
                    v = b[u][x]
                    if v not in seen3:
                        seen3.add(v)
                        order2.append(v)
            if order2 != list(range(m)):
                continue
            found.append(b)
        autos.append(found)

    for i in range(len(autos)):
        for j in range(len(autos)):
            left = autos[i]
            right = autos[j]
            # skip trivial all-blank pair unless it works
            ctx = closure(left, right)
            if ctx is None:
                continue
            cert = {
                "kind": "cps",
                "left": left,
                "right": right,
                "contexts": to_ctx_dict(ctx),
            }
            try:
                kind = check(tm, cert)
                if kind is not None:
                    return cert
            except Reject:
                continue
    return None
