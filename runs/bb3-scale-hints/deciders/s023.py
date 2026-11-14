import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# CPS certificate attempt by enumerating small automata for the two half-tapes.
# We build a DFA over alphabet {0,1} (0 = blank, 1 = non-zero) for each side,
# then compute the least closed context set and check that no context halts.

def _build_context_closure(tm, left, right, limit_ctx=200000):
    # tm parsed: table[(state, symbol)] -> (write, move, next_state) ; states int
    table, n_states, n_symbols = parse(tm)
    # context: (l, q, s, r) where l,left-state; q, machine state; s, symbol under head (0/1); r, right-state
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = list(ctx)
    while frontier:
        if len(ctx) > limit_ctx:
            return None
        nxt = []
        for (l, q, s, r) in frontier:
            if (q, s) not in table:
                return None  # halting context -> reject
            w, move, q2 = table[(q, s)]
            if move == 1:
                l2 = left[l][w] if l < len(left) else None
                if l2 is None:
                    return None
                # for EVERY pair (r2, s2) with right[r2][s2] == r
                pairs = [(r2, s2) for r2 in range(len(right)) for s2 in (0, 1)
                         if right[r2][s2] == r]
                for (r2, s2) in pairs:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        nxt.append(c)
            else:  # move == -1
                r2 = right[r][w] if r < len(right) else None
                if r2 is None:
                    return None
                pairs = [(l2, s2) for l2 in range(len(left)) for s2 in (0, 1)
                         if left[l2][s2] == l]
                for (l2, s2) in pairs:
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        nxt.append(c)
        frontier = nxt
    return ctx

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # Try all pairs of automata with sizes up to 3 for each side.
    # state 0 loops on symbol 0 (blank) -> left[0][0] == right[0][0] == 0
    # Automata are deterministic: for each state, transitions on 0 and 1.
    # Enumerate all deterministic transition tables of size n (state 0 on 0 must go to 0).
    def enumerate_autos(n):
        # each state: (t0, t1) where t0,t1 in range(n); state 0 t0 = 0
        # represented as list of n pairs
        if n == 1:
            yield [[0, 0]]
            return
        # recursive enumeration over states 1..n-1 for simplicity, state 0 fixed
        def rec(state, acc):
            if state == n:
                yield acc
                return
            for t0 in range(n):
                for t1 in range(n):
                    if state == 0 and t0 != 0:
                        continue
                    acc.append([t0, t1])
                    yield from rec(state + 1, acc)
                    acc.pop()
        yield from rec(0, [])
    # limit total work
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            for L in enumerate_autos(nl):
                if L[0][0] != 0:
                    continue
                for R in enumerate_autos(nr):
                    if R[0][0] != 0:
                        continue
                    ctx = _build_context_closure(tm, L, R)
                    if ctx is None:
                        continue
                    # Build certificate
                    cert = {
                        "kind": "cps",
                        "left": L,
                        "right": R,
                        "contexts": [[l, q, s, r] for (l, q, s, r) in ctx],
                    }
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None
