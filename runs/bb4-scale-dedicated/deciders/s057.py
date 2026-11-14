import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- helpers ----------

def blank_ctx_closure(tm, left, right, cap_ctx=200000, cap_states=5000):
    """Given two DFA tables left/right (dict (state,sym)->state or None),
    close the cps context set starting from [0,0,0,0].
    Returns (contexts, ok) where ok is False if any context is halting or
    the closure exceeds limits. Contexts are tuples (l,q,s,r)."""
    table, n_states, n_symbols = parse(tm)
    # state letters: A=0, B=1, ...
    contexts = set()
    stack = [(0, 0, 0, 0)]
    contexts.add((0, 0, 0, 0))
    while stack:
        l, q, s, r = stack.pop()
        tr = table.get((q, s))
        if tr is None:
            return None, False
        w, move, q2 = tr
        if move == 1:
            l2 = left.get((l, w))
            if l2 is None:
                return None, False
            # pop one symbol s2 from right: right[r2][s2] == r
            for (r2, s2), rr in right.items():
                if rr == r:
                    for s3 in (0, 1):
                        # the symbol under the head is now s2? No: after moving right,
                        # the head is on the cell that was at the far side of the window.
                        # Standard construction: the new head symbol is s2 (the cell just
                        # entered from the right half-tape).
                        pass
            # simpler: the new head symbol is the cell that was immediately to the
            # right, i.e. the symbol s2 with right[r2][s2] == r. That symbol is now
            # under the head. So new context is (l2, q2, s2, r2).
            for (r2, s2), rr in list(right.items()):
                if rr == r:
                    c = (l2, q2, s2, r2)
                    if c not in contexts:
                        contexts.add(c)
                        stack.append(c)
        else:
            r2 = right.get((r, w))
            if r2 is None:
                return None, False
            for (l2, s2), ll in list(left.items()):
                if ll == l:
                    c = (l2, q2, s2, r2)
                    if c not in contexts:
                        contexts.add(c)
                        stack.append(c)
        if len(contexts) > cap_ctx:
            return None, False
    return contexts, True

# ---------- DFA enumeration ----------

def enumerate_dfa_tables(n_states, n_symbols, cap_states=5000):
    """Yield deterministic transition tables (dict) of exactly n_states states
    where state 0 loops on symbol 0. BFS-canonical: transitions are filled in
    order (state, sym) = (0,0),(0,1),(1,0),... with targets in 0..n_states-1.
    To keep it tractable we restrict: state 0 on symbol 0 -> 0, and we generate
    all tables where each (state,sym) maps to a state >= previous target or equal
    (canonical form to avoid duplicates up to state renaming)."""
    keys = [(st, sy) for st in range(n_states) for sy in range(n_symbols)]
    # force (0,0)->0
    fixed = {(0, 0): 0}
    free = [k for k in keys if k not in fixed]
    # generate all assignments
    import itertools
    for combo in itertools.product(range(n_states), repeat=len(free)):
        t = dict(fixed)
        for k, v in zip(free, combo):
            t[k] = v
        yield t

# ---------- backward analysis ----------

def backward_halting_set(tm, cap=20000):
    """States (q) from which the machine can reach a halting transition.
    Approximation: mark states that have at least one halting transition,
    then propagate backwards through transitions that lead to marked states."""
    table, n_states, n_symbols = parse(tm)
    # build reverse edges
    rev = {q: [] for q in range(n_states)}
    halt_states = set()
    for (q, s), (w, mv, q2) in table.items():
        rev[q2].append(q)
        # halting transition is absent; detect by checking if (q,s) not in table
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                halt_states.add(q)
    # propagate: if q has a transition to a halting state, q can halt
    changed = True
    while changed:
        changed = False
        for q in range(n_states):
            if q in halt_states:
                continue
            for s in range(n_symbols):
                tr = table.get((q, s))
                if tr is None:
                    halt_states.add(q); changed = True; break
                w, mv, q2 = tr
                if q2 in halt_states:
                    halt_states.add(q); changed = True; break
    return halt_states

# ---------- main decider ----------

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    halt_states = backward_halting_set(tm)

    # Try small DFAs for the left half-tape first (1..3 states), then right.
    for n in (1, 2, 3):
        for lt in enumerate_dfa_tables(n, 2):
            # quick check: state 0 must not be able to reach a halting state
            # in the automaton sense: any symbol read from the blank tape
            # leads to state 0; if the machine can halt with blank left half-tape,
            # this DFA is useless. We approximate by checking that state 0
            # does not force a halt: skip detailed check, rely on closure.
            for m in (1, 2, 3):
                for rt in enumerate_dfa_tables(m, 2):
                    contexts, ok = blank_ctx_closure(tm, lt, rt)
                    if ok:
                        left = [[lt.get((i, x)) for x in range(2)] for i in range(n)]
                        right = [[rt.get((i, x)) for x in range(2)] for i in range(m)]
                        # contexts: list of [l,q,s,r]
                        ctx = [list(c) for c in contexts]
                        cert = {"kind": "cps", "left": left, "right": right, "contexts": ctx}
                        try:
                            check(tm, cert)
                        except Reject:
                            continue
                        return cert
    return None

if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    c = decide(tm)
    print(c if c else None)