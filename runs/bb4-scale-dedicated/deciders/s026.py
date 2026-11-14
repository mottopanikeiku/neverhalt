NAME = "dfa-search-cps"

from neverhalt.tm import parse, run


def _halting_states(table, n_states):
    # transitions that would halt: next_state out of range or absent
    states = set()
    for (q, s), t in table.items():
        w, m, n2 = t
        if n2 is None or n2 < 0 or n2 >= n_states:
            states.add((q, s))
    return states


def _can_reach_halt_left(tm, n_states, n_symbols):
    # For pruning: does the left automaton's language (read far to head)
    # over symbol 0 strings have to contain a tape that reaches a halting
    # transition? We approximate by checking whether blank-left context can
    # reach a context whose (q,s) halts. Simpler conservative check: if any
    # halting transition exists with q reachable from 0 on all-zero input.
    # We use a coarse reachability on the machine state graph ignoring tape.
    return None


def _transitions_from_machine(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _enum_dfa_tables(n_states, n_symbols):
    # yield transition tables for a DFA with states 0..n-1, state 0 loops on 0
    # (blank tape must be a fixed point). Enumerate all maps to states.
    import itertools
    idx = list(range(n_states))
    # left automaton reads far-to-head; state 0 on symbol 0 must stay 0
    # for the blank tape to be accepted as context.
    for combo in itertools.product(idx, repeat=n_states * n_symbols):
        tab = [[None] * n_symbols for _ in range(n_states)]
        ok = True
        for i in range(n_states):
            for x in range(n_symbols):
                tab[i][x] = combo[i * n_symbols + x]
        # state 0 loops on symbol 0
        if tab[0][0] != 0:
            continue
        yield tab


def _dfa_from_table(tab):
    # kernel wants left[i][x] int or null; use None for null and -1 -> None
    return tab


def _closure_contexts(tm, left, right, n_states):
    table, ns, nsym = parse(tm)
    # context: (l, q, s, r)
    seen = set()
    stack = [(0, 0, 0, 0)]
    while stack:
        ctx = stack.pop()
        if ctx in seen:
            continue
        seen.add(ctx)
        l, q, s, r = ctx
        if q >= ns:
            return None  # halting context -> reject
        if (q, s) not in table:
            return None
        w, m, q2 = table[(q, s)]
        if q2 is None or q2 < 0 or q2 >= ns:
            return None
        if m == +1:
            if left[l][w] is None:
                return None
            l2 = left[l][w]
            for r2 in range(len(right)):
                for s2 in range(nsym):
                    if right[r2][s2] == r:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in seen:
                            stack.append(nctx)
        else:
            if right[r][w] is None:
                return None
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in range(nsym):
                    if left[l2][s2] == l:
                        nctx = (l2, q2, s2, r2)
                        if nctx not in seen:
                            stack.append(nctx)
    return seen


def decide(tm):
    table, ns, nsym = parse(tm)
    # Try small DFAs for the left half-tape, up to 3 states for speed.
    for nl in (1, 2, 3):
        for left in _enum_dfa_tables(nl, nsym):
            # The right automaton can be the same table or its mirror; try
            # both the same enumeration and the identity-ish table.
            for nr in (1, 2, 3):
                for right in _enum_dfa_tables(nr, nsym):
                    # quick sanity: blank tape context must be closed
                    if left[0][0] != 0 or right[0][0] != 0:
                        continue
                    ctxs = _closure_contexts(tm, left, right, ns)
                    if ctxs is None:
                        continue
                    if (0, 0, 0, 0) not in ctxs:
                        continue
                    # no halting context by construction (closure returns None)
                    # Emit certificate with pruned tables.
                    def prune(tab, ctxs):
                        used = set()
                        for (l, q, s, r) in ctxs:
                            used.add(l)
                        out = [[None] * nsym for _ in range(len(tab))]
                        for i in range(len(tab)):
                            for x in range(nsym):
                                if tab[i][x] is not None and any(
                                    c[0] == i and c[2] == x for c in ctxs
                                ):
                                    out[i][x] = tab[i][x]
                        return out
                    return {
                        "kind": "cps",
                        "left": prune(left, ctxs),
                        "right": prune(right, ctxs),
                        "contexts": [list(c) for c in ctxs],
                    }
    return None
