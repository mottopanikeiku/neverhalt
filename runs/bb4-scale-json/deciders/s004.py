from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

import sys

def decide(tm):
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    # Search for a translated cycle (tcycle) around a window.
    # For 4-state machines, a common shape: a "bouncing" pattern that
    # shifts by +1 or -1 each lap.  We simulate up to a bounded horizon
    # and look for a lap where the window contents are reproduced and
    # the far-side cells are blank.
    MAX_T = 4000
    MAX_P = 4000

    try:
        halted, steps, state, pos, tape = run(tm, MAX_T + MAX_P + 10)
    except Exception:
        return None

    if halted:
        return None

    # Snapshot tape at T and T+P for candidate windows.
    # We only need tape at two times; run gives us the final time.
    # To get intermediate snapshots we re-run with different bounds.
    try:
        h1, s1, st1, p1, tape1 = run(tm, MAX_T + MAX_P + 5)
    except Exception:
        return None

    # Re-simulate collecting snapshots at chosen times.
    # Simple approach: collect snapshots every step up to horizon.
    H = 3000
    if H > 600:
        H = 600

    try:
        # Collect tape snapshots at each step up to H
        from neverhalt.tm import parse as _parse, run as _run
        # We need a step-by-step simulator; implement a local one.
        table, ns, nsym = parse(tm)
        tape = {}
        state = 0
        head = 0
        snapT = []
        snapP = []
        snapStep = []
        # snapshot dict: position -> symbol
        def snap():
            return dict(tape)
        snapT.append(snap())
        snapStep.append(0)
        halted = False
        for i in range(1, 2400):
            if (state, tape.get(head, 0)) not in table:
                halted = True
                break
            w, mv, nxt = table[(state, tape.get(head, 0))]
            tape[head] = w
            head += mv
            state = nxt
            snapT.append(snap())
            snapStep.append(i)
            if halted:
                break
        if halted:
            return None
    except Exception:
        return None

    n = len(snapT)
    if n < 100:
        return None

    # Try all pairs (T, T+P) with P in some range, looking for a lap
    # where state matches and window contents reproduce shifted.
    # Search limited to keep under budget.
    import itertools

    best = None
    # candidate T values: multiples of small numbers
    Ts = list(range(20, min(n - 40, 800), 1))
    Ps = list(range(10, 200, 1))

    for T in Ts:
        if T + 200 >= n:
            break
        stT = None
        # recover state at T: we didn't store state. Re-run to T and store states.
        break

    # Redo simulation storing states at each step.
    try:
        table, ns, nsym = parse(tm)
        tape = {}
        state = 0
        head = 0
        states = [0]
        heads = [0]
        snaps = [dict(tape)]
        for i in range(1, 2400):
            key = (state, tape.get(head, 0))
            if key not in table:
                break
            w, mv, nxt = table[key]
            tape[head] = w
            head += mv
            state = nxt
            states.append(state)
            heads.append(head)
            snaps.append(dict(tape))
        n = len(snaps)
        if n < 100:
            return None
    except Exception:
        return None

    # Look for translated cycle.
    # For each T, for each P, check state match and window translation.
    # Use a coarse search: P in [10, 300], T in [50, 800].
    # To keep time bounded, sample T.
    found = None
    Ts = range(40, min(900, n - 100), 4)
    for T in Ts:
        for P in range(10, 260, 2):
            if T + P >= n:
                break
            if states[T] != states[T + P]:
                continue
            t1 = snaps[T]
            t2 = snaps[T + P]
            d = heads[T + P] - heads[T]
            if d == 0:
                # plain cycle: check window same
                # find window [lo, hi] covering all nonzero in t1
                lo = min(t1.keys()) if t1 else 0
                hi = max(t1.keys()) if t1 else 0
                ok = all(t2.get(y, 0) == t1.get(y, 0) for y in range(lo, hi + 1))
                if ok:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
                continue
            # translated: d > 0 or d < 0
            # window: positions seen during lap
            lo = min(heads[T:T + P + 1])
            hi = max(heads[T:T + P + 1])
            ok = True
            for y in range(lo, hi + 1):
                if t2.get(y + d, 0) != t1.get(y, 0):
                    ok = False
                    break
            if not ok:
                continue
            if d > 0:
                # every cell right of hi blank at T+P
                for y in range(hi + 1, hi + 200):
                    if t2.get(y, 0) != 0:
                        ok = False
                        break
            else:
                for y in range(lo - 200, lo):
                    if t2.get(y, 0) != 0:
                        ok = False
                        break
            if ok:
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass

    # If no cycle found, try n-gram CPS with small n.
    def build_cps(tm, ngram):
        table, ns, nsym = parse(tm)
        # Build automata for left and right half tapes.
        # State = ngram tuple of bits (from far to near).
        # left: reads cells left of head from far away towards head.
        # right: reads cells right of head from far away towards head.
        # For simplicity, we build automata that remember last k cells.
        def build_side(k):
            states = {}
            trans = {}
            def idx(t):
                if t not in states:
                    states[t] = len(states)
                return states[t]
            idx(())
            # closure
            changed = True
            while changed:
                changed = False
                for t in list(states.keys()):
                    i = states[t]
                    for x in (0, 1):
                        nt = (t + (x,))[-k:] if k > 0 else ()
                        j = idx(nt)
                        if (i, x) not in trans:
                            trans[(i, x)] = j
                            changed = True
            # build as list of lists
            m = len(states)
            arr = [[None, None] for _ in range(m)]
            for (i, x), j in trans.items():
                arr[i][x] = j
            return arr, states

        try:
            left, lmap = build_side(ngram)
            right, rmap = build_side(ngram)
        except Exception:
            return None

        # contexts: [l, q, s, r]
        # start [0,0,0,0] must be a context.
        # BFS closure.
        if lmap.get(()) != 0 or rmap.get(()) != 0:
            return None
        if left[0][0] != 0 or right[0][0] != 0:
            return None

        contexts = set()
        contexts.add((0, 0, 0, 0))
        frontier = [(0, 0, 0, 0)]
        while frontier:
            l, q, s, r = frontier.pop()
            key = (q, s)
            if key not in table:
                return None  # halting context
            w, mv, q2 = table[key]
            if mv == 1:
                if left[l][w] is None:
                    return None
                l2 = left[l][w]
                for r2, s2 in list(rmap.items()):
                    if rmap and False:
                        pass
                # find all (r2, s2) with right[r2][s2] == r
                pairs = []
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right[r2][s2] == r:
                            pairs.append((r2, s2))
                for r2, s2 in pairs:
                    c = (l2, q2, s2, r2)
                    if c not in contexts:
                        contexts.add(c)
                        frontier.append(c)
            else:
                if right[r][w] is None:
                    return None
                r2 = right[r][w]
                pairs = []
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left[l2][s2] == l:
                            pairs.append((l2, s2))
                for l2, s2 in pairs:
                    c = (l2, q2, s2, r2)
                    if c not in contexts:
                        contexts.add(c)
                        frontier.append(c)

        if len(contexts) > 200000:
            return None

        left_tab = [[a, b] for a, b in left]
        right_tab = [[a, b] for a, b in right]
        ctx_list = [[l, q, s, r] for (l, q, s, r) in contexts]
        cert = {"kind": "cps", "left": left_tab, "right": right_tab, "contexts": ctx_list}
        try:
            check(tm, cert)
            return cert
        except Reject:
            return None

    for ng in range(1, 5):
        c = build_cps(tm, ng)
        if c is not None:
            return c

    return None
} 