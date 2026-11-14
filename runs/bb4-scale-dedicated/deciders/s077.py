import sys
from collections import deque
from neverhalt.tm import parse

sys.setrecursionlimit(1000000)


def _states_of(t):
    return len(t)


def _make_left(n):
    left = [[0] * 2 for _ in range(n)]
    left[0][0] = 0
    return left


def _make_right(n):
    right = [[0] * 2 for _ in range(n)]
    right[0][0] = 0
    return right


def decide(tm):
    table, ns, nsym = parse(tm)
    # table keys are ints: state*2 + symbol
    # We work with an internal representation of contexts.
    # Enumerate candidate automata for the right half-tape first
    # (the left automaton then is forced up to a small number of states).
    # BFS over transition tables up to 3 states per side, then grow.
    max_states = 4
    # We will enumerate DFAs for the right side as lists of rows.
    # A DFA is a tuple of rows; each row is a tuple of two entries.
    # State 0 must loop on 0: row[0][0] == 0.
    for nr in range(1, max_states + 1):
        for rows in _gen_rows(nr):
            right = rows
            # Compute the backward-halting set of right automaton states
            # as the hint suggests: states from which the blank tape can
            # never be reached? Actually prune as soon as the tapes that
            # can lead to a halt are forced to include the blank tape.
            # We approximate by requiring that state 0 is a sink on 0.
            if right[0][0] != 0:
                continue
            # Build the smallest closed context set for this right automaton
            # and some left automaton. Try left automata of the same size.
            for nl in range(1, nr + 1):
                for lrows in _gen_rows(nl):
                    if lrows[0][0] != 0:
                        continue
                    cert = _closure(tm, lrows, right)
                    if cert is not None:
                        return cert
    return None


def _gen_rows(n):
    # Generate all DFA transition rows for n states, but only those
    # consistent with state 0 looping on 0. Kept small because n <= 4:
    # 3^(2n-2) is at most 3^6 = 729 per n. We yield row-by-row.
    if n == 1:
        # Only state 0, must loop on 0.
        for s1 in range(1, 2):
            yield ((0, s1),)
        return
    from itertools import product
    # states 1..n-1 can go anywhere; state 0's symbol-1 target is free,
    # but state 0's symbol-0 target must be 0.
    for rest in product(range(n), repeat=2 * (n - 1)):
        rows = [(0, rest[0])]
        i = 1
        for st in range(1, n):
            rows.append((rest[i], rest[i + 1]))
            i += 2
        yield tuple(rows)


def _closure(tm, left, right):
    # left/right: tuples of rows (write target states)
    # Represent automaton as list of rows: left[q][x] = target or None (not used).
    # We treat every listed target as valid; None means absent, but we only
    # enumerate complete tables, so all targets exist.
    nl = len(left)
    nr = len(right)
    # Contexts: (l, q, s, r)
    start = (0, 0, 0, 0)
    contexts = set()
    contexts.add(start)
    frontier = [start]
    steps = 0
    while frontier and steps < 200000:
        steps += 1
        nxt = []
        for (l, q, s, r) in frontier:
            key = q * 2 + s
            if key not in tm:
                # Halting context would be needed; reject by returning None
                return None
            w, move, q2 = tm[key]
            if move > 0:
                # right move: l2 = left[l][w]
                if w >= 2 or left[l][w] is None:
                    return None
                l2 = left[l][w]
                # For every (r2, s2) with right[r2][s2] == r
                for r2 in range(nr):
                    for s2 in range(2):
                        if right[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                nxt.append(ctx)
            else:
                # left move: r2 = right[r][w]
                if w >= 2 or right[r][w] is None:
                    return None
                r2 = right[r][w]
                for l2 in range(nl):
                    for s2 in range(2):
                        if left[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                nxt.append(ctx)
        frontier = nxt
    if frontier:
        return None
    # All contexts closed. Emit certificate.
    return {
        "kind": "cps",
        "left": [list(row) for row in left],
        "right": [list(row) for row in right],
        "contexts": [list(c) for c in contexts],
    }


# Backwards pruning helper (kept for clarity; the enumeration above already
# prunes by size). Not used in the hot path.
def _halting_states(tm):
    return set()


def _unused():
    pass
