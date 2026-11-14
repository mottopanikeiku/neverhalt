import sys
from collections import deque
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _halt_set(table, ns, nq):
    # Backwards: configurations (q, s) that can reach a halt.
    # We work with (state, symbol) pairs that occur; halting means no
    # transition for (q, s).
    bad = set()
    changed = True
    # Build predecessor graph on (q,s) -> (q',s') pairs.
    preds = {}
    for (q, s), (w, mv, q2) in table.items():
        for s2 in (0, 1):
            if (q2, s2) in table or True:
                preds.setdefault((q2, s2), []).append((q, s, w, mv))
    # A (q,s) is bad if it has no transition (halt) OR all successors are bad.
    # Successors of (q,s): after writing w and moving, the next symbol read is
    # s2 which can be anything; the successor pair is (q2, s2) for the symbol
    # that will be read next. For non-halting analysis we treat both symbols.
    # Compute greatest fixed point of "can reach a halt".
    # Start: pairs with no transition are halting (bad).
    for q in range(ns):
        for s in (0, 1):
            if (q, s) not in table:
                bad.add((q, s))
    changed = True
    while changed:
        changed = False
        for (q, s), (w, mv, q2) in table.items():
            if (q, s) in bad:
                continue
            # successors: (q2, 0) and (q2, 1)
            if all((q2, s2) in bad for s2 in (0, 1)):
                bad.add((q, s))
                changed = True
    return bad


def _dfa_steps(nstates, nsteps):
    # Yield DFA transition tables: list of lists, entry is state or None.
    # symbols 0 and 1; state 0 must loop on 0 (blank half-tape self-loop).
    if nstates < 1:
        return
    # Represent table as tuple of tuples
    table = [[None, None] for _ in range(nstates)]
    table[0][0] = 0
    idx = list(range(nstates))
    def rec(i):
        if i == nstates * 2:
            yield tuple(tuple(row) for row in table)
            return
        st = i // 2
        sym = i % 2
        if st == 0 and sym == 0:
            yield from rec(i + 1)
            return
        for v in [None] + idx:
            table[st][sym] = v
            yield from rec(i + 1)
    yield from rec(0)


def _closure contexts(left, right, table, ns, nq):
    # left/right: list of lists (entry or None).  nq = number of machine states
    # Build context set as frozenset of (l, q, s, r).
    ctx = set()
    # BFS from (0, 0, 0, 0)
    start = (0, 0, 0, 0)
    ctx.add(start)
    dq = deque([start])
    nctx_states = len(left) * nq * 2 * len(right)
    while dq:
        l, q, s, r = dq.popleft()
        if (q, s) not in table:
            return None  # halting context reached
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            l2 = left[l][w] if l < len(left) else None
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            dq.append(c)
        else:
            r2 = right[r][w] if r < len(right) else None
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            dq.append(c)
    if len(ctx) > 200000:
        return None
    return ctx


def decide(tm):
    table, ns, nq = parse(tm)
    # Machine states 0..ns-1; symbols 0,1.  table keys (state, symbol).
    # Note parse returns states as ints with A=0 already.
    # Quick: simulate to know it does not halt in 300 steps (all holdouts).
    # We do not need that here; we search for a CPS certificate.
    # Search over left DFA sizes 1..4 first, then right DFA derived.
    # For each candidate left DFA, compute right DFA as reverse-determinized
    # language of the "bad" set: actually we try to find any right DFA such
    # that closure is non-halting.  Simpler: search both sides small.
    # Time budget is tight (500 ms); do a bounded search.
    import time
    t0 = time.time()
    # Precompute halting pairs
    for nstates_l in range(1, 5):
        if time.time() - t0 > 0.30:
            break
        for nstates_r in range(1, 5):
            if nstates_l + nstates_r > 6:
                continue
            for lt in _dfa_steps(nstates_l, 2):
                if time.time() - t0 > 0.30:
                    break
                for rt in _dfa_steps(nstates_r, 2):
                    ctx = _closure_contexts(lt, rt, table, ns, nq)
                    if ctx is not None:
                        left = [[a, b] for a, b in lt]
                        right = [[a, b] for a, b in rt]
                        contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                        cert = {"kind": "cps", "left": left, "right": right,
                                "contexts": contexts}
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None
