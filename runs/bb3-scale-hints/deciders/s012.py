import sys
from collections import deque

# --- Decider: finite-automaton search over small half-tape automata (farside -> head) ---
# Strategy (per the hint): enumerate DFA transition tables for the left half-tape in
# BFS-canonical order with growing state count (start from 1 state, grow up to a cap),
# but prune a partial table as soon as it is forced to accept the blank tape as a
# halting witness.  For each surviving left DFA we do the closed-context fixpoint and
# check the kernel.  We also try the cheap "reversed" variant: enumerate DFAs for the
# right half-tape by the same search and then reverse-determinize symbolically via the
# context closure, which is exactly what the kernel's context set computes anyway.

HALT = None

# symbol alphabet is {0,1}; automaton states are 0..n-1 with 0 == all-blank half-tape
# left[i][x] = next state reading cell x (x=0 is blank), or None if unreachable.

def _is_blank_state(trans, n):
    # state 0 must loop on 0 and be the all-blank state
    return trans[0][0] == 0

def _complete(trans):
    # fill missing entries deterministically (a fresh sink state) -> for search only
    # returns (trans, n) with all entries present
    n = len(trans)
    for i in range(n):
        row = trans[i]
        for x in (0, 1):
            if row[x] is None:
                row[x] = n
                n += 1
                trans.append([0, 0])
                trans[-1][0] = n - 1
                trans[-1][1] = n - 1
    return trans, n

def _closure_contexts(left, right, n_states, q0, s0):
    # fixed point over contexts [l, q, s, r]; returns dict or None if a halting
    # context is forced (i.e. the machine halts => certificate unusable)
    ctx = set()
    ctx.add((0, q0, s0, 0))
    frontier = [(0, q0, s0, 0)]
    while frontier:
        l, q, s, r = frontier.pop()
        if q >= n_states:
            return None  # halting context reached -> cannot prove non-halting
        # transition of the machine on (q, s)
        key = (q, s)
        step = _TM[key]
        if step is None:
            return None
        w, move, q2 = step
        if move == +1:
            # right move: push w onto left half-tape; pop nearest right cell
            l2 = left[l][w]
            if l2 is None:
                return None
            # every (r2, s2) with right[r2][s2] == r must be covered
            for r2 in range(len(right)):
                row = right[r2]
                for s2 in (0, 1):
                    if row[s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
        else:
            # left move: mirror
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                row = left[l2]
                for s2 in (0, 1):
                    if row[s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in ctx:
                            ctx.add(c)
                            frontier.append(c)
    return ctx

def _emit(tm):
    # parse the machine into _TM[(q,s)] = (w, move, q2) or None for halting
    global _TM, _NS
    from neverhalt.tm import parse
    table, ns, nsym = parse(tm)
    _NS = ns
    _TM = {}
    for q in range(ns):
        for s in (0, 1):
            v = table.get((q, s))
            if v is None:
                _TM[(q, s)] = None
            else:
                w, mv, q2 = v
                _TM[(q, s)] = (w, mv, q2)
    # quick check: if the machine actually halts, no certificate is possible
    from neverhalt.tm import run
    halted, steps, st, pos, tape = run(tm, 200)
    if halted:
        return None

    # We search over left DFAs first, then over right DFAs.  The kernel's context
    # invariant needs both automata; we grow one side and let the other be the
    # trivial all-blank half-tape first, then mirror.
    best = None
    # --- enumerate left DFAs with 1..MAX states (BFS canonical, rows for symbols 0,1) ---
    MAX = 4
    # start with 1-state automaton: state 0 loops on 0 (blank), 1 is also 0 (blank)
    rows0 = [[0, 0]]
    candidates = []
    # generate all tables over states 0..n-1 that are "reachable-consistent":
    # state 0 must loop on 0 and all states must be reachable from 0 on some string.
    def gen(n):
        # enumerate all functions {0..n-1} x {0,1} -> {0..n-1}
        total = n * n
        for code in range(total ** 2):
            t = []
            c = code
            for i in range(n):
                row = []
                for x in (0, 1):
                    row.append(c % total)
                    c //= total
                t.append(row)
            # canonical: state 0 must loop on 0
            if t[0][0] != 0:
                continue
            # reachability from 0
            seen = {0}
            stack = [0]
            while stack:
                u = stack.pop()
                for x in (0, 1):
                    v = t[u][x]
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            if seen != set(range(n)):
                continue
            candidates.append(t)
    for n in range(1, MAX + 1):
        gen(n)
        # try each candidate as the left automaton, with the trivial right automaton
        # (state 0 loops on both symbols: right half-tape is all blank).
        for L in candidates[-(len(candidates)):] if False else []:
            pass
        # note: we build right as trivial for now
        for L in ([c for c in candidates if len(c) == n]):
            R = [[0, 0]]  # trivial right automaton (all-blank)
            ctx = _closure_contexts(L, R, ns, 0, 0)
            if ctx is None:
                continue
            if len(ctx) > 200000:
                continue
            left_tbl = [[L[i][x] for x in (0, 1)] for i in range(len(L))]
            right_tbl = [[0, 0]]
            contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
            cert = {"kind": "cps", "left": left_tbl, "right": right_tbl,
                    "contexts": contexts}
            from neverhalt.kernel import check, Reject
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    # --- mirror: enumerate right DFAs with trivial left automaton ---
    for n in range(1, MAX + 1):
        for R in ([c for c in candidates if len(c) == n]):
            L = [[0, 0]]
            ctx = _closure_contexts(L, R, ns, 0, 0)
            if ctx is None or len(ctx) > 200000:
                continue
            left_tbl = [[0, 0]]
            right_tbl = [[R[i][x] for x in (0, 1)] for i in range(len(R))]
            contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
            cert = {"kind": "cps", "left": left_tbl, "right": right_tbl,
                    "contexts": contexts}
            from neverhalt.kernel import check, Reject
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None

def decide(tm: str):
    try:
        return _emit(tm)
    except Exception:
        return None