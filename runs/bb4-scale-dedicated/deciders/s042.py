from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

import itertools


def _states_of(n):
    return list(range(n))


def _context_key(ctx):
    return ctx


def _closure_contexts(tm, n_states, left, right):
    """Smallest closed context set, or None if a halting context is forced.

    left/right: list of lists of ints or None, indexed by automaton state.
    Returns (contexts, ok) where contexts is a list of (l, q, s, r).
    """
    n_q = len(tm)
    tab = tm
    start = (0, 0, 0, 0)
    seen = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            entry = tab[(q, s)]
            if entry is None:
                return None, False
            w, mv, q2 = entry
            if mv > 0:
                l2 = left[l][w]
                if l2 is None:
                    return None, False
                for (r2, s2) in itertools.product(range(len(right)), range(2)):
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            nxt.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None, False
                for (l2, s2) in itertools.product(range(len(left)), range(2)):
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            nxt.append(c)
        frontier = nxt
    return sorted(seen), True


def _emit(tm, left, right, contexts):
    cert = {
        "kind": "cps",
        "left": [[None if x is None else x for x in row] for row in left],
        "right": [[None if x is None else x for x in row] for row in right],
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert


def _all_tables(n_states):
    """All deterministic tables on symbols {0,1} with state 0 looping on 0."""
    states = _states_of(n_states)
    out = []
    choices = [(a, b) for a in states for b in states]
    for combo in itertools.product(choices, repeat=n_states):
        tab = [[0] * 2 for _ in states]
        for i, st in enumerate(states):
            for x in (0, 1):
                tab[i][x] = combo[i][x]
        # state 0 must loop on symbol 0
        if tab[0][0] != 0:
            continue
        out.append(tab)
    return out


def decide(tm_str):
    try:
        tm, n_states, n_symbols = parse(tm_str)
    except Exception:
        return None
    if n_states > 5:
        return None

    # Precompute all tables of size 1..3 for both sides.
    cache = {}
    for n in (1, 2, 3):
        cache[n] = _all_tables(n)

    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            for left in cache[nl]:
                for right in cache[nr]:
                    if len(left) * len(right) > 2500:
                        continue
                    contexts, ok = _closure_contexts(tm, n_states, left, right)
                    if not ok:
                        continue
                    cert = _emit(tm, left, right, contexts)
                    if cert is not None:
                        return cert
    return None
