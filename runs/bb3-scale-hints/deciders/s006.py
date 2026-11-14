import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- helpers ----------

def _halt_states(n):
    return list(range(n))

def _parse_tm(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

def _step_states(n_states):
    # all possible states reachable from A (state 0) in principle
    return list(range(n_states))

# Compute, for each (q, s), the "forced blank" reachability: the set of
# contexts (by their l,r automaton states) that are reachable.  We do the
# closure directly as the kernel does.

def _context_closure(transition, left, right, n_states, max_ctx=200000):
    """transition: dict (q,s)->(w,move,q2) or None if halting.
       left[i][x], right[i][x]: automaton targets or None.
       Returns (contexts_set, halting_context_found)"""
    # start context
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    halting = False
    while stack:
        if len(seen) > max_ctx:
            return None, True
        (l, q, s, r) = stack.pop()
        tr = transition.get((q, s))
        if tr is None:
            halting = True
            return None, True
        w, move, q2 = tr
        if move == 1:
            l2 = left[l][w]
            if l2 is None:
                # context cannot be extended -> this branch is dead (fine)
                continue
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(len(right[r2])):
                    if right[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = right[r][w]
            if r2 is None:
                continue
            for l2 in range(len(left)):
                for s2 in range(len(left[l2])):
                    if left[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    return seen, False

# ---------- search ----------

def _enumerate_automata(n_states, n_symbols):
    """Yield every deterministic automaton with states 0..n_states-1
       reading symbols 0..n_symbols-1, as a tuple of tuples (targets).
       State 0 loops on symbol 0 (blank half-tape).  We enumerate all
       target functions, but require left[0][0]==0 and right[0][0]==0
       (kernel rule)."""
    # target for (state, symbol) must be in 0..n_states-1 or None.
    # Enumerate via recursion over all (state, symbol) pairs.
    pairs = [(i, x) for i in range(n_states) for x in range(n_symbols)]
    total = (n_states + 1) ** len(pairs)
    if total > 12_000_000:
        return
    for mask in range(total):
        m = mask
        table = []
        for _ in range(n_states):
            row = []
            for _ in range(n_symbols):
                v = m % (n_states + 1)
                m //= (n_states + 1)
                row.append(None if v == n_states else v)
            table.append(tuple(row))
        table = tuple(table)
        if table[0][0] != 0:
            continue
        # symbol 1 transitions: we allow anything, but the kernel requires
        # right[0][0]==0 too; left is forced, right will be checked later.
        yield table

def _canonical_automata(n_states, n_symbols):
    """BFS-canonical order: prefer smaller target ids, i.e. enumerate by
       a canonical ordering of the target function.  Simplest: enumerate
       all and sort by a rank that favors small targets."""
    out = []
    for t in _enumerate_automata(n_states, n_symbols):
        # rank: tuple of targets in BFS order
        out.append(t)
    out.sort(key=lambda t: tuple(
        t[i][x] if t[i][x] is not None else n_states
        for i in range(n_states) for x in range(n_symbols)))
    return out

def _try_pair(tm, table, n_states, transition):
    n_symbols = 2  # always 2-symbol machines
    # left automaton
    try:
        left_list = _canonical_automata(1, n_symbols)
    except Exception:
        left_list = [tuple((0, 0))]
    if not left_list:
        return None
    left = left_list[0]
    # right automaton: search small ones
    for rsize in (1, 2, 3):
        for right in _canonical_automata(rsize, n_symbols):
            # kernel requires right[0][0]==0
            if right[0][0] != 0:
                continue
            # left[0][0]==0 already true
            ctxs, halting = _context_closure(transition, left, right,
                                             n_states)
            if halting:
                continue
            if ctxs is None:
                continue
            # convert to certificate
            left_tbl = [[left[i][x] for x in range(n_symbols)]
                        for i in range(len(left))]
            right_tbl = [[right[i][x] for x in range(n_symbols)]
                         for i in range(len(right))]
            contexts = [[l, q, s, r] for (l, q, s, r) in ctxs]
            cert = {"kind": "cps", "left": left_tbl, "right": right_tbl,
                    "contexts": contexts}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                continue
    return None

def decide(tm: str):
    table, n_states, n_symbols = parse(tm)
    # build transition dict
    transition = {}
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) in table:
                w, move, q2 = table[(q, s)]
                transition[(q, s)] = (w, move, q2)
            else:
                transition[(q, s)] = None
    # quick cycle check first (cheap)
    try:
        halted, steps, state, pos, tape = run(tm, 100000)
        if halted:
            return None
    except Exception:
        pass
    # Try tiny automata pairs: left = 1 state (blank loop), right = 1..3
    # Then left = 2, right = 1..2, etc.
    for lsize in (1, 2):
        for ltab in _canonical_automata(lsize, n_symbols):
            if ltab[0][0] != 0:
                continue
            for rsize in (1, 2, 3):
                for rtab in _canonical_automata(rsize, n_symbols):
                    if rtab[0][0] != 0:
                        continue
                    ctxs, halting = _context_closure(transition, ltab, rtab,
                                                     n_states)
                    if halting or ctxs is None:
                        continue
                    left_tbl = [[ltab[i][x] for x in range(n_symbols)]
                                for i in range(lsize)]
                    right_tbl = [[rtab[i][x] for x in range(n_symbols)]
                                 for i in range(rsize)]
                    contexts = [[l, q, s, r] for (l, q, s, r) in ctxs]
                    cert = {"kind": "cps", "left": left_tbl,
                            "right": right_tbl, "contexts": contexts}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
                    except Exception:
                        continue
    return None
