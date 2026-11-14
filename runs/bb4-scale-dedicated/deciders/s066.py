import sys
from collections import deque

from neverhalt.tm import parse, run

T_LIMIT = 100000


def _load(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols


def _build_automata(n_states, bits):
    """Return all deterministic automata over {0,1} with n_states states.

    State 0 is the all-blank half-tape: automaton[0][0] == 0.
    The table is a tuple of pairs; None means 'never happens'.
    """
    out = []
    for rows in range(n_states):
        for bits_ in range((2 ** n_states) ** 2):
            row = []
            ok = True
            for x in range(2):
                row.append((bits_ >> (rows * 2 + x)) & 1)
            # state 0 must loop on symbol 0
            if row[0] != 0:
                continue
            out.append(tuple(row))
    return out


def _closure(table, n_states, n_symbols, left, right):
    """Smallest closed context set for a (left, right) automaton pair.

    Returns (contexts, ok) where contexts is the closed set (a set of tuples)
    and ok is False if the set is empty or contains a halting context.
    """
    contexts = set()
    frontier = [(0, 0, 0, 0)]
    contexts.add((0, 0, 0, 0))
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if s >= n_symbols or (q, s) not in table:
                return None, False
            w, move, q2 = table[(q, s)]
            if move == 1:
                l2 = left[l][w]
                if l2 is None:
                    return None, False
                for (r2, s2) in _pairs_with_target(right, r):
                    item = (l2, q2, s2, r2)
                    if item not in contexts:
                        contexts.add(item)
                        nxt.append(item)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None, False
                for (l2, s2) in _pairs_with_target(left, l):
                    item = (l2, q2, s2, r2)
                    if item not in contexts:
                        contexts.add(item)
                        nxt.append(item)
        frontier = nxt
    if (0, 0, 0, 0) not in contexts:
        return None, False
    return contexts, True


def _pairs_with_target(aut, target):
    """All (source, symbol) pairs in aut whose transition lands in target."""
    res = []
    n = len(aut)
    for src in range(n):
        for sym in range(2):
            v = aut[src][sym]
            if v == target:
                res.append((src, sym))
    return res


def decide(tm):
    table, n_states, n_symbols = _load(tm)
    if n_symbols != 2:
        return None
    # Search small automata on both sides.
    max_states = 3
    candidates = []
    for size in range(1, max_states + 1):
        candidates.extend(_build_automata(size, 2))
    # Sort by size then lexicographic for determinism.
    candidates.sort(key=lambda a: (len(a), a))
    seen = set()
    for left in candidates:
        key = left
        if key in seen:
            continue
        seen.add(key)
        for right in candidates:
            if right in seen:
                # still try, but avoid duplicate pair expansion
                pass
            contexts, ok = _closure(table, n_states, n_symbols, left, right)
            if ok and contexts is not None:
                cert = {
                    "kind": "cps",
                    "left": [list(row) for row in left],
                    "right": [list(row) for row in right],
                    "contexts": [list(c) for c in contexts],
                }
                return cert
    return None


if __name__ == "__main__":
    import json
    import sys
    tm = sys.argv[1]
    print(json.dumps(decide(tm)))
