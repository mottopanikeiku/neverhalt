"""Decider: search small DFAs per side, then closed-context fixpoint.

Strategy:
 1. Enumerate DFA transition tables for the left half-tape (far-to-head) with
    1..3 states, state 0 loops on symbol 0 (blank tape accepted).
 2. Prune a partial table as soon as the blank tape is forced into the
    language (i.e. some state that can be reached on the all-blank suffix can
    loop on all blanks and the table is closed there) -- such an automaton
    would make the blank tape a context, forcing a halting context.
 3. For each surviving pair of (left, right) automata, run the closed-context
    fixpoint: start from [0,0,0,0] and add contexts required by every step.
    Reject if any required context halts or the closure is not finite.
 4. Emit the certificate with only the transitions the closure used (null
    elsewhere) to stay under the kernel limits.
"""

from neverhalt.tm import parse


def _language_ok(table, n, max_states):
    """table: dict (i,x) -> j or None (None = dead). Partial allowed.
    Return True if the all-blank tape (all zeros) is NOT accepted:
    i.e. there is no closed loop of zeros from state 0. A partial table is
    OK if it cannot be completed into an accepting blank tape: the only
    closed zero-loop reachable from 0 must pass through a state with an
    undefined zero transition, or 0 has no zero-loop."""
    seen = set()
    stack = [0]
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        seen.add(i)
        if i == 0:
            # zero-loop from 0 -> blank tape accepted -> reject
            return False
        j = table.get((i, 0))
        if j is None:
            # undefined: cannot accept blank tape through here
            continue
        stack.append(j)
    return True


def _all_tables(n, size):
    """Yield complete transition tables for `n` states, symbols {0,1},
    with the constraint table[(0,0)] = 0."""
    cells = [(i, x) for i in range(n) for x in (0, 1)]
    cells.remove((0, 0))
    import itertools
    for combo in itertools.product(range(n), repeat=len(cells)):
        t = {(0, 0): 0}
        for c, v in zip(cells, combo):
            t[c] = v
        yield t


def _closure(tm, left, right, max_ctx=200000):
    """Closed-context fixpoint. Returns (contexts, ok).
    contexts: list of [l,q,s,r]."""
    table, n_states, n_symbols = parse(tm)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if len(contexts) > max_ctx:
                return [], False
            if (q, s) not in table:
                return [], False  # halting context
            w, move, q2 = table[(q, s)]
            if move == 1:  # right move
                l2 = left.get((l, w))
                if l2 is None:
                    return [], False
                for r2 in range(len(right)):
                    for s2 in (0, 1):
                        if right.get((r2, s2)) == r:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                nxt.append(c)
            else:  # left move
                r2 = right.get((r, w))
                if r2 is None:
                    return [], False
                for l2 in range(len(left)):
                    for s2 in (0, 1):
                        if left.get((l2, s2)) == l:
                            c = (l2, q2, s2, r2)
                            if c not in contexts:
                                contexts.add(c)
                                nxt.append(c)
        frontier = nxt
    return sorted(contexts), True


def _prune_used(left, contexts):
    used = set()
    for (l, q, s, r) in contexts:
        used.add((l, 0))
        used.add((l, 1))
    t = {}
    for (l, x) in used:
        if left.get((l, x)) is not None:
            t[(l, x)] = left[(l, x)]
    return t


def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    max_states = 3
    for n in range(1, max_states + 1):
        for lt in _all_tables(n, n):
            if not _language_ok(lt, n, n):
                continue
            for m in range(1, max_states + 1):
                for rt in _all_tables(m, m):
                    if not _language_ok(rt, m, m):
                        continue
                    L = dict(lt)
                    R = dict(rt)
                    ctx, ok = _closure(tm, L, R)
                    if ok and ctx:
                        Lu = _prune_used(L, ctx)
                        Ru = _prune_used(R, ctx)
                        cert = {
                            "kind": "cps",
                            "left": [[None if (i, x) not in Lu else Lu[(i, x)]
                                      for x in (0, 1)] for i in range(n)],
                            "right": [[None if (i, x) not in Ru else Ru[(i, x)]
                                       for x in (0, 1)] for i in range(m)],
                            "contexts": [list(c) for c in ctx],
                        }
                        return cert
    return None
