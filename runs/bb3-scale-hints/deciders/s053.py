from neverhalt.tm import parse, run

# --------------------------------------------------------------------------
# Decider: "cps_search"  -  search over small half-tape automata instead of
# designed n-gram ones.
#
# Strategy
#   * for each machine, take its transitions and check whether the state
#     space can be covered by a *closed* set of contexts [l, q, s, r] where
#     l and r index DFAs over the two half-tapes.
#   * Enumerate DFA transition tables with 1, 2, 3 states per side, with
#     state 0 looping on symbol 0 (state 0 = all-blank half-tape), and
#     compute the smallest closed context set for each pair.  If no
#     context halts, emit the certificate with only the used transitions.
# --------------------------------------------------------------------------

import itertools

HALT = None


def _transitions(tm):
    """Return {(q, s): (w, move, q2)} for defined transitions."""
    table, ns, nsym = parse(tm)
    out = {}
    for (q, s), t in table.items():
        out[(q, s)] = t
    return out, ns


def _build_tables(ns):
    """All transition tables over states range(ns) x {0,1} -> state in range(ns),
    with state 0 looping on 0 (left[0][0]=right[0][0]=0)."""
    states = ns
    for size in (2, 3):
        for entry in itertools.product(range(size), repeat=states * 2):
            left = [list(entry[2 * i:2 * i + 2]) for i in range(states)]
            right = [list(entry[states * 2 + 2 * i:states * 2 + 2 * i + 2]) for i in range(states)]
            if left[0][0] != 0:
                continue
            yield left, right


def _determinize(transitions, ns, side):
    """For a fixed other half-tape automaton, compute the set of (r2, s2)
    with right[r2][s2] == r (or left[l][s2] == l).  Used to expand a
    context by one step, then close."""
    # side == 'right' means we expand the left automaton using right
    # automaton targets.  Precompute for each automaton state all pairs.
    other = None
    return None


def _close_contexts(transitions, ns, left, right):
    """Smallest closed context set containing [0,0,0,0].
    Returns (contexts, halting_found, uses) or None if no start needed."""
    # map (l, q, s, r) -> True
    contexts = set()
    stack = [(0, 0, 0, 0)]
    contexts.add((0, 0, 0, 0))
    # which transitions of the automata are actually used
    used = [[False, False] for _ in range(len(left))]
    usedr = [[False, False] for _ in range(len(right))]

    while stack:
        (l, q, s, r) = stack.pop()
        t = transitions.get((q, s))
        if t is None:
            return None, True, used, usedr   # halting context found
        w, move, q2 = t
        if move == +1:
            # right move: written w goes onto left half-tape
            if left[l][w] is None:
                return None, True, used, usedr
            l2 = left[l][w]
            used[l][w] = True
            # right automaton pops nearest cell: every (r2, s2) with
            # right[r2][s2] == r gives a new context
            for r2 in range(len(right)):
                for s2 in (0, 1):
                    if right[r2][s2] == r:
                        key = (l2, q2, s2, r2)
                        if key not in contexts:
                            contexts.add(key)
                            stack.append(key)
        else:
            # left move: written w goes onto right half-tape
            if right[r][w] is None:
                return None, True, used, usedr
            r2 = right[r][w]
            usedr[r][w] = True
            for l2 in range(len(left)):
                for s2 in (0, 1):
                    if left[l2][s2] == l:
                        key = (l2, q2, s2, r2)
                        if key not in contexts:
                            contexts.add(key)
                            stack.append(key)
    return contexts, False, used, usedr


def _emit(transitions, ns, left, right, contexts, used, usedr):
    """Trim automata to used transitions, emit certificate."""
    L = len(left)
    R = len(right)
    Lout = [[None, None] for _ in range(L)]
    for i in range(L):
        for x in (0, 1):
            if used[i][x]:
                Lout[i][x] = left[i][x]
    Rout = [[None, None] for _ in range(R)]
    for i in range(R):
        for x in (0, 1):
            if usedr[i][x]:
                Rout[i][x] = right[i][x]
    # state 0 must loop on symbol 0
    Lout[0][0] = 0
    Rout[0][0] = 0
    ctx = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": Lout, "right": Rout, "contexts": ctx}


def decide(tm):
    try:
        transitions, ns = _transitions(tm)
    except Exception:
        return None

    # The machine's state count is 2 or 3; try automata of growing size.
    for size in (2, 3):
        for left, right in _build_tables(ns):
            contexts, halting, used, usedr = _close_contexts(
                transitions, ns, left, right)
            if contexts is None:
                continue
            if halting:
                continue
            cert = _emit(transitions, ns, left, right, contexts, used, usedr)
            return cert
    return None