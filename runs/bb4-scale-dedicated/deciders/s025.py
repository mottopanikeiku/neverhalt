import sys
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

# Shared helpers: build automaton tables and check closure.

def _is_canonical(table, n):
    # table: list of lists of ints or None; canonical means reachable states are ordered by first appearance
    seen = [False]*n
    order = []
    dq = [0]
    seen[0] = True
    while dq:
        s = dq.pop(0)
        order.append(s)
        for x in range(2):
            t = table[s][x]
            if t is not None and not seen[t]:
                seen[t] = True
                dq.append(t)
    return order

def _closure_contexts(left, right, nq, ns):
    # left[i][x], right[i][x]: automaton transitions, None means impossible.
    # Contexts: (l, q, s, r)
    # Build all (l,q,s,r) reachable from (0,0,0,0) under the CPS rules.
    # The rules:
    #  - context must have a machine transition (q,s) = (w, move, q2) with q2 < nq
    #  - if move == +1: l2 = left[l][w]; for every (r2,s2) with right[r2][s2]==r, [l2,q2,s2,r2] must be context
    #  - if move == -1: r2 = right[r][w]; for every (l2,s2) with left[l2][s2]==l, [l2,q2,s2,r2] must be context
    # We find the smallest closed set. If none, context set would be empty (impossible from start), but
    # we need to check the start context itself has a transition.
    # Precompute reverse maps: for right automaton: for each state r, list of (r2,s2) with right[r2][s2]==r
    # for left: for each state l, list of (l2,s2) with left[l2][s2]==l
    rev_right = [[[] for _ in range(ns)] for _ in range(ns)]
    for r2 in range(ns):
        for s2 in range(2):
            t = right[r2][s2]
            if t is not None:
                rev_right[t].append((r2, s2))
    rev_left = [[[] for _ in range(ns)] for _ in range(ns)]
    for l2 in range(ns):
        for s2 in range(2):
            t = left[l2][s2]
            if t is not None:
                rev_left[t].append((l2, s2))
    # automaton transitions for left/right: they are deterministic; we need all states that can
    # be reached. We'll compute the fixpoint.
    # Start context (0,0,0,0) must exist and have a transition.
    start = (0, 0, 0, 0)
    # BFS over contexts
    from collections import deque
    seen = set()
    dq = deque()
    seen.add(start)
    dq.append(start)
    contexts = []
    ok = True
    while dq:
        ctx = dq.popleft()
        contexts.append(ctx)
        l, q, s, r = ctx
        # machine transition
        tr = table_m[q][s]
        if tr is None:
            ok = False
            break
        w, move, q2 = tr
        if move == 1:  # right move
            l2 = left[l][w]
            if l2 is None:
                ok = False
                break
            # for every (r2,s2) with right[r2][s2]==r, add (l2,q2,s2,r2)
            for (r2, s2) in rev_right[r]:
                nctx = (l2, q2, s2, r2)
                if nctx not in seen:
                    seen.add(nctx)
                    dq.append(nctx)
        else:  # left move
            r2 = right[r][w]
            if r2 is None:
                ok = False
                break
            for (l2, s2) in rev_left[l]:
                nctx = (l2, q2, s2, r2)
                if nctx not in seen:
                    seen.add(nctx)
                    dq.append(nctx)
    if not ok:
        return None
    # Check no context halts: we already ensured every context has a transition, but we must
    # also ensure that the start context exists and the set is closed. The BFS above only adds
    # contexts that are required; if a required context has no transition, we fail.
    # Also, the kernel requires [0,0,0,0] in contexts, which it is.
    return contexts

def _emit_cps(left, right, contexts, nq):
    # Convert automaton tables to kernel format: null for None.
    def conv(tab, n):
        return [[tab[i][x] for x in range(2)] for i in range(n)]
    # left/right must have state 0 looping on symbol 0 as per hint but kernel just needs tables.
    # We keep only states that appear in contexts to reduce size.
    used_left = sorted(set(c[0] for c in contexts))
    used_right = sorted(set(c[3] for c in contexts))
    # remap states to 0..k-1, ensuring 0 is start (it is in contexts)
    def remap(used, tab, n):
        mp = {s: i for i, s in enumerate(used)}
        newn = len(used)
        newtab = [[None, None] for _ in range(newn)]
        for s in used:
            i = mp[s]
            for x in range(2):
                t = tab[s][x]
                if t is not None:
                    newtab[i][x] = mp.get(t, None)
        return newtab, newn
    ltab, ln = remap(used_left, left, len(left))
    rtab, rn = remap(used_right, right, len(right))
    # contexts: remap automaton states
    newctx = [[mp_l[c[0]], c[1], c[2], mp_r[c[3]]] for c in contexts for mp_l, mp_r in [(dict(zip(used_left, range(len(used_left)))), dict(zip(used_right, range(len(used_right)))))] ]
    # simpler:
    mp_l = {s: i for i, s in enumerate(used_left)}
    mp_r = {s: i for i, s in enumerate(used_right)}
    newctx = [[mp_l[c[0]], c[1], c[2], mp_r[c[3]]] for c in contexts]
    return {"kind": "cps", "left": ltab, "right": rtab, "contexts": newctx}

# Global machine table set by decide
table_m = None
nq = None

# Enumerate automata in BFS-canonical order: deterministic transitions on {0,1}, state 0 loops on 0.
# We enumerate all tables for n states (up to max_states) that are reachable from 0 and canonical
# (states in BFS order). To keep it simple and fast, we enumerate all tables and filter canonical.

def enumerate_automata(max_states, time_limit):
    import time
    t0 = time.time()
    for n in range(1, max_states+1):
        # all functions from n*2 inputs to n outputs
        total = n**(2*n)
        # generate via recursion with pruning: state 0 must loop on 0
        # We'll do iterative deepening: build table row by row.
        rows = []
        def rec(i):
            if time.time() - t0 > time_limit:
                raise TimeoutError
            if i == n:
                # canonical check: BFS from 0, states in order 0..n-1
                seen = [False]*n
                dq = [0]
                seen[0] = True
                order = []
                while dq:
                    s = dq.pop(0)
                    order.append(s)
                    for x in range(2):
                        t = rows[s][x]
                        if t is not None and not seen[t]:
                            seen[t] = True
                            dq.append(t)
                if order != list(range(n)):
                    return
                yield [row[:] for row in rows]
                return
            for x in range(2):
                # state 0 on symbol 0 must be 0
                if i == 0 and x == 0:
                    vals = [0]
                else:
                    vals = list(range(n))
                for v in vals:
                    rows[i][x] = v
                    yield from rec(i+1 if x == 1 else i)
                    if time.time() - t0 > time_limit:
                        raise TimeoutError
            rows[i][0] = rows[i][1] = None
        # implement recursion properly: we need to yield tables. Rewrite as generator.
        def gen(i, x):
            if time.time() - t0 > time_limit:
                raise TimeoutError
            if i == n:
                # canonical check
                seen = [False]*n
                dq = [0]
                seen[0] = True
                order = []
                while dq:
                    s = dq.pop(0)
                    order.append(s)
                    for xx in range(2):
                        t = rows[s][xx]
                        if t is not None and not seen[t]:
                            seen[t] = True
                            dq.append(t)
                if order != list(range(n)):
                    return
                yield [row[:] for row in rows]
                return
            if x == 0:
                if i == 0:
                    vals = [0]
                else:
                    vals = list(range(n))
                for v in vals:
                    rows[i][0] = v
                    yield from gen(i, 1)
            else:
                # symbol 1: any state or None? Kernel allows null? The automaton table entries are
                # ints or null. The hint says null if that never happens. So we allow None.
                for v in list(range(n)) + [None]:
                    rows[i][1] = v
                    yield from gen(i+1, 0)
                rows[i][1] = None
        rows = [[None, None] for _ in range(n)]
        try:
            yield from gen(0, 0)
        except TimeoutError:
            return

# Reverse-determinize an NFA to a DFA (far-to-head reading). We use it for the partner side.
# Given an NFA with states 0..m-1, transitions nfa[state][sym] = set of next states, start set {0},
# accepting set = states from which a halting context could be reached? The hint says:
# "the tapes that can lead to a halt (computed backwards from the halting transitions) are forced
# to include the blank tape". We compute the set of automaton states (for one half-tape) that can
# lead to a halt, then reverse-determinize the complement language into a DFA.
# For simplicity, we will try both automata from the enumeration and check closure directly;
# if closure succeeds, we emit. This is a brute-force search over pairs of small automata.

def try_pair(left, right, nq, ns):
    global table_m
    contexts = _closure_contexts(left, right, nq, ns)
    if contexts is None:
        return None
    if len(contexts) > 200000:
        return None
    if len(left) > 5000 or len(right) > 5000:
        return None
    cert = _emit_cps(left, right, contexts, nq)
    try:
        from neverhalt.kernel import check
        check(tm, cert)
        return cert
    except Exception:
        return None

def decide(tm: str):
    global table_m, nq
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    # table[(state, symbol)] = (write, move, next_state); halting transitions absent
    # Build table_m[q][s] = (w, move, q2) or None
    table_m = [[None, None] for _ in range(n_states)]
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
                table_m[q][s] = (w, move, q2)
    nq = n_states
    # Time budget: 500 ms per machine. We'll set a short internal limit.
    import time
    t0 = time.time()
    limit = 0.45
    max_states = 4  # try small first
    # Enumerate automata for left and right. To save time, we'll enumerate all automata up to
    # max_states and try all pairs. If time runs out, return None.
    autos = []
    for n in range(1, max_states+1):
        for aut in enumerate_automata(n, limit):
            autos.append(aut)
            if time.time() - t0 > limit:
                break
        if time.time() - t0 > limit:
            break
    # If enumeration timed out, we may have partial autos; try pairs anyway.
    # To avoid O(n^2) blowup, limit number of autos.
    if len(autos) > 200:
        autos = autos[:200]
    for left in autos:
        if time.time() - t0 > limit:
            break
        for right in autos:
            if time.time() - t0 > limit:
                break
            cert = try_pair(left, right, nq, len(left))
            if cert is not None:
                return cert
    return None

# The above is a first attempt; we need to make it actually work. Let's simplify and make it robust:
# We'll do a direct search: enumerate automata up to 3 states, try all pairs, and return first cert.
# We'll also include a fallback: if no cert, return None.

def decide(tm: str):
    import time
    from neverhalt.tm import parse
    from neverhalt.kernel import check
    t0 = time.time()
    limit = 0.45
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    table_m = [[None, None] for _ in range(n_states)]
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
                table_m[q][s] = (w, move, q2)
    nq = n_states
    # Enumerate automata up to 3 states, canonical.
    autos = []
    for n in range(1, 4):
        for aut in enumerate_automata(n, limit):
            autos.append(aut)
            if time.time() - t0 > limit:
                break
        if time.time() - t0 > limit:
            break
    if len(autos) > 300:
        autos = autos[:300]
    for left in autos:
        if time.time() - t0 > limit:
            break
        for right in autos:
            if time.time() - t0 > limit:
                break
            cert = try_pair(left, right, nq, len(left))
            if cert is not None:
                return cert
    return None

# We need to fix the generator: the recursive enumerate_automata has a bug (rows not reset properly).
# Let's rewrite it cleanly as a simple generator that builds all tables via itertools.product.

def enumerate_automata_clean(max_states, time_limit):
    import time
    from itertools import product
    t0 = time.time()
    for n in range(1, max_states+1):
        # each state has 2 transitions, each can be 0..n-1 or None
        choices = list(range(n)) + [None]
        for combo in product(choices, repeat=2*n):
            if time.time() - t0 > time_limit:
                return
            tab = [list(combo[2*i:2*i+2]) for i in range(n)]
            # canonical: BFS from 0 must visit states in order 0..n-1
            seen = [False]*n
            dq = [0]
            seen[0] = True
            order = []
            while dq:
                s = dq.pop(0)
                order.append(s)
                for x in range(2):
                    t = tab[s][x]
                    if t is not None and not seen[t]:
                        seen[t] = True
                        dq.append(t)
            if order != list(range(n)):
                continue
            # state 0 loops on symbol 0
            if tab[0][0] != 0:
                continue
            yield tab

def decide(tm: str):
    import time
    from neverhalt.tm import parse
    from neverhalt.kernel import check
    t0 = time.time()
    limit = 0.45
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    table_m = [[None, None] for _ in range(n_states)]
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
                table_m[q][s] = (w, move, q2)
    nq = n_states
    autos = []
    for n in range(1, 4):
        for aut in enumerate_automata_clean(n, limit):
            autos.append(aut)
            if time.time() - t0 > limit:
                break
        if time.time() - t0 > limit:
            break
    if len(autos) > 400:
        autos = autos[:400]
    for left in autos:
        if time.time() - t0 > limit:
            break
        for right in autos:
            if time.time() - t0 > limit:
                break
            cert = try_pair(left, right, nq, len(left))
            if cert is not None:
                return cert
    return None

# try_pair and _closure_contexts and _emit_cps are defined above. We'll re-define them here for
# completeness in this module. (The earlier definitions are included, but we need them defined
# before decide is called. Python resolves at call time, so order doesn't matter as long as
# they are defined in the module.)

# However, the earlier definitions reference 'table_m' and 'nq' globals. We set them in decide.
# We must ensure _closure_contexts uses table_m. It does.
# The _emit_cps function has a bug in remapping; let's rewrite it cleanly.

def _emit_cps(left, right, contexts, nq):
    used_left = sorted(set(c[0] for c in contexts))
    used_right = sorted(set(c[3] for c in contexts))
    mp_l = {s: i for i, s in enumerate(used_left)}
    mp_r = {s: i for i, s in enumerate(used_right)}
    def conv(tab, used, mp):
        n = len(used)
        newtab = [[None, None] for _ in range(n)]
        for s in used:
            i = mp[s]
            for x in range(2):
                t = tab[s][x]
                if t is not None:
                    newtab[i][x] = mp.get(t, None)
        return newtab
    ltab = conv(left, used_left, mp_l)
    rtab = conv(right, used_right, mp_r)
    newctx = [[mp_l[c[0]], c[1], c[2], mp_r[c[3]]] for c in contexts]
    return {"kind": "cps", "left": ltab, "right": rtab, "contexts": newctx}

def _closure_contexts(left, right, nq, ns):
    from collections import deque
    # left/right are lists of [t0, t1] with ints or None.
    # reverse maps
    rev_right = [[[] for _ in range(ns)] for _ in range(ns)]
    for r2 in range(ns):
        for s2 in range(2):
            t = right[r2][s2]
            if t is not None:
                rev_right[t].append((r2, s2))
    rev_left = [[[] for _ in range(ns)] for _ in range(ns)]
    for l2 in range(ns):
        for s2 in range(2):
            t = left[l2][s2]
            if t is not None:
                rev_left[t].append((l2, s2))
    start = (0, 0, 0, 0)
    seen = set()
    dq = deque([start])
    seen.add(start)
    contexts = []
    while dq:
        l, q, s, r = dq.popleft()
        contexts.append((l, q, s, r))
        if q >= nq or s >= 2:
            return None
        tr = table_m[q][s]
        if tr is None:
            return None
        w, move, q2 = tr
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for (r2, s2) in rev_right[r]:
                nctx = (l2, q2, s2, r2)
                if nctx not in seen:
                    seen.add(nctx)
                    dq.append(nctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for (l2, s2) in rev_left[l]:
                nctx = (l2, q2, s2, r2)
                if nctx not in seen:
                    seen.add(nctx)
                    dq.append(nctx)
    if len(contexts) > 200000:
        return None
    return contexts

def try_pair(left, right, nq, ns):
    contexts = _closure_contexts(left, right, nq, ns)
    if contexts is None:
        return None
    if len(left) > 5000 or len(right) > 5000:
        return None
    cert = _emit_cps(left, right, contexts, nq)
    try:
        from neverhalt.kernel import check
        check(tm, cert)
        return cert
    except Exception:
        return None

# Final decide: we need to reference the global tm inside try_pair. Let's make it a parameter.
# We'll rewrite try_pair to accept tm.

def _try_pair(tm, left, right, nq, ns):
    contexts = _closure_contexts(left, right, nq, ns)
    if contexts is None:
        return None
    if len(left) > 5000 or len(right) > 5000:
        return None
    cert = _emit_cps(left, right, contexts, nq)
    try:
        from neverhalt.kernel import check
        check(tm, cert)
        return cert
    except Exception:
        return None

def decide(tm: str):
    import time
    from neverhalt.tm import parse
    t0 = time.time()
    limit = 0.45
    parsed = parse(tm)
    table, n_states, n_symbols = parsed
    global table_m, nq
    table_m = [[None, None] for _ in range(n_states)]
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
                table_m[q][s] = (w, move, q2)
    nq = n_states
    autos = []
    for n in range(1, 4):
        for aut in enumerate_automata_clean(n, limit):
            autos.append(aut)
            if time.time() - t0 > limit:
                break
        if time.time() - t0 > limit:
            break
    if len(autos) > 400:
        autos = autos[:400]
    for left in autos:
        if time.time() - t0 > limit:
            break
        for right in autos:
            if time.time() - t0 > limit:
                break
            cert = _try_pair(tm, left, right, nq, len(left))
            if cert is not None:
                return cert
    return None
