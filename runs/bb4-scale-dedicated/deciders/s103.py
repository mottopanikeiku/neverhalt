import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---- helpers ---------------------------------------------------------------

def transitions(parsed):
    table, n_states, n_symbols = parsed
    return table, n_states, n_symbols

def halt_states(parsed):
    # states q such that some transition halts
    table, n_states, n_symbols = parsed
    hs = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                hs.add(q)
    return hs

def build_halting_contexts(parsed):
    """Return set of (q, s) that can reach a halting transition in the
    machine's own transition graph (ignoring tape symbols)."""
    table, n_states, n_symbols = parsed
    # reverse reachability from halting transitions
    succ = {q: set() for q in range(n_states)}
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                succ[q].add(q2)
    target = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                target.add(q)
    # states that can reach target
    reach = set(target)
    changed = True
    while changed:
        changed = False
        for q in range(n_states):
            if q in reach:
                continue
            if succ[q] & reach:
                reach.add(q)
                changed = True
    # contexts (q,s) whose successors lead to halting states
    ctx = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                if q2 in reach:
                    ctx.add((q, s))
    return ctx

# ---- DFA enumeration (BFS canonical) --------------------------------------

def enum_dfa_tables(max_states, n_symbols):
    """Enumerate deterministic automata with states 0..k-1, state 0 loops
    on symbol 0 (blank), in BFS-canonical order by size."""
    results = []
    for k in range(1, max_states + 1):
        # canonical: start with k states, state 0 loops on 0
        # enumerate all tables with states 0..k-1 where state 0 on symbol 0 -> 0
        # simple odometer enumeration
        import itertools
        if k > 3:
            # too many; skip beyond 3
            break
        cells = [(q, s) for q in range(k) for s in range(n_symbols) if not (q == 0 and s == 0)]
        for combo in itertools.product(range(k), repeat=len(cells)):
            tbl = [[None] * n_symbols for _ in range(k)]
            tbl[0][0] = 0
            for (q, s), nxt in zip(cells, combo):
                tbl[q][s] = nxt
            results.append((k, tbl))
    return results

# ---- closure ---------------------------------------------------------------

def close_contexts(parsed, left, right):
    table, n_states, n_symbols = parsed
    halt = halt_states(parsed)
    # initial context
    init = (0, 0, 0, 0)
    seen = {init}
    stack = [init]
    while stack:
        l, q, s, r = stack.pop()
        if (q, s) not in table:
            return None  # halting context reached
        w, mv, q2 = table[(q, s)]
        if mv == 1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(len(right)):
                for s2 in range(n_symbols):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(len(left)):
                for s2 in range(n_symbols):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            stack.append(c)
    # emit certificate
    left_ctx = [[left[i][x] for x in range(n_symbols)] for i in range(len(left))]
    right_ctx = [[right[i][x] for x in range(n_symbols)] for i in range(len(right))]
    contexts = [[l, q, s, r] for (l, q, s, r) in seen]
    return {"kind": "cps", "left": left_ctx, "right": right_ctx, "contexts": contexts}

# ---- main ------------------------------------------------------------------

def decide(tm):
    try:
        parsed = parse(tm)
    except Exception:
        return None
    table, n_states, n_symbols = parsed

    # quick check: run a bit; if it halts, nothing to prove
    try:
        halted, steps, st, pos, tape = run(tm, 200)
        if halted:
            return None
    except Exception:
        return None

    # enumerate small left automata
    for k, left in enum_dfa_tables(3, n_symbols):
        # skip automata that can reach a halt from blank via some path? do it lazily
        # build right automaton: reverse of left (far-to-head). For a DFA left
        # reading far-to-head, the right reading far-to-head is the reverse
        # language. Build an NFA reversal then determinize.
        # Simplified: try right = left for now (both directions symmetric-ish),
        # and also reversed left.
        cands = [left]
        # reversed table as DFA approximation
        rev = [[None] * n_symbols for _ in range(k)]
        for i in range(k):
            for x in range(n_symbols):
                if left[i][x] is not None:
                    # reverse edge: from x-state to i on symbol x is not a DFA
                    pass
        cands.append(left)
        for right in cands:
            cert = close_contexts(parsed, left, right)
            if cert:
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
                except Exception:
                    pass
    return None

NAME = "dfa-search-1" if False else "small-cps-search"
