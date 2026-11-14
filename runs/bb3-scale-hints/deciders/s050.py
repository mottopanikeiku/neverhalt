import itertools
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# BFS-canonical enumeration of half-tape automata, plus a closed-context fixpoint.
# For each candidate DFA (state 0 loops on 0), build the smallest context set
# containing [0,0,0,0] and closed under the one-step expansion rule; emit a
# certificate as soon as the closure contains no halting context.

def _build_automaton(n_states, allowed):
    # automaton: state i on symbol x -> state, or None. State 0 loops on 0.
    table = [[None, None] for _ in range(n_states)]
    for i in range(n_states):
        if i == 0:
            table[0][0] = 0
        else:
            table[i][0] = allowed.pop() if allowed else None
    return table

def _closure_contexts(left, right, n_states, n_syms, trans):
    # context = (l, q, s, r). Expansion: for right move, for every (r2,s2) with
    # right[r2][s2] == r, the new context (left[l][w], q2, s2, r2) must exist.
    # For left move, mirror. Start with [0,0,0,0], close under expansion.
    contexts = {(0, 0, 0, 0)}
    frontier = list(contexts)
    while frontier:
        l, q, s, r = frontier.pop()
        if (q, s) not in trans:
            return None  # halting context: this candidate fails
        w, move, q2 = trans[(q, s)]
        if move == +1:
            l2 = left[l][w]
            if l2 is None:
                return None
            for r2 in range(n_states):
                for s2 in range(n_syms):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            frontier.append(c)
        else:
            r2 = right[r][w]
            if r2 is None:
                return None
            for l2 in range(n_states):
                for s2 in range(n_syms):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in contexts:
                            contexts.add(c)
                            frontier.append(c)
    return contexts

def decide(tm):
    try:
        table, n_states, n_syms = parse(tm)
    except Exception:
        return None
    trans = {}
    for st in range(n_states):
        for sy in range(n_syms):
            v = table.get((st, sy))
            if v is not None:
                w, move, q2 = v
                trans[(st, sy)] = (w, move, q2)
    # Enumerate DFAs for one half-tape up to 4 states, then 5, canonical order.
    for n in range(1, 5):
        for bits in _dfa_assignments(n, n_syms):
            left = bits
            # closure check with right = same automaton (symmetric first try)
            ctx = _closure_contexts(left, left, n, n_syms, trans)
            if ctx is not None:
                cert = {"kind": "cps", "left": left, "right": left,
                        "contexts": [[l, q, s, r] for (l, q, s, r) in ctx]}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    return None

def _dfa_assignments(n, n_syms):
    # enumerate deterministic transition tables for n states where state 0 loops
    # on 0; canonical BFS order by number of transitions then lexicographic.
    out = []
    choices = [None] * n_syms
    def rec(i, acc):
        if i == n:
            out.append([list(row) for row in acc])
            return
        # state i: symbol 0 is fixed to 0 for state 0; other symbols may be any
        # state or None (meaning "never reached").
        for sym in range(n_syms):
            row = [None, None]
            if i == 0:
                row[0] = 0
            for target in [None] + list(range(n)):
                row[sym] = target
                rec(i + 1, acc + [row])
                row[sym] = None
    rec(0, [])
    # sort by number of non-None entries then lexicographic
    out.sort(key=lambda t: (sum(1 for row in t for x in row if x is not None), t))
    return out

NAME = "cps_search"