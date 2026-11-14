"""Search half-tape automata for surviving bouncer holdouts.

Strategy: enumerate DFA transition tables for one half-tape (state 0 loops on
symbol 0).  For each table, compute the smallest closed context set for the
machine, using the mirror of the table for the other half-tape.  Stop at the
first table whose closure is non-empty and contains no halting context.  Emit
the certificate with only the transitions the closure actually used.
"""

from neverhalt.tm import parse
from neverhalt.kernel import Reject, check

import itertools


def _build_tables(n_states, n_symbols):
    """All tables with states 0..n_states-1, symbols 0..n_symbols-1.

    Yields (table, used) where table[i][x] is target state or None.
    State 0 loops on symbol 0 (the all-blank half-tape).
    """
    if n_states == 1:
        # only state 0, which must loop on 0
        yield [[0] * n_symbols]
        return
    choices = list(range(n_states)) + [None]
    for i in range(n_states):
        for x in range(n_symbols):
            if i == 0 and x == 0:
                continue
            yield from ()  # placeholder to keep structure clear
    # generator over full assignments below
    idx = 0
    total = len(choices) ** (n_states * n_symbols - 1)
    # too many for large sizes; we only call with small sizes
    for combo in itertools.product(choices, repeat=n_states * n_symbols - 1):
        table = [[None] * n_symbols for _ in range(n_states)]
        table[0][0] = 0
        k = 0
        for i in range(n_states):
            for x in range(n_symbols):
                if i == 0 and x == 0:
                    continue
                table[i][x] = combo[k]
                k += 1
        yield table


def _closure(tm, left, right, n_states):
    """Smallest closed context set for the machine under (left, right).

    Returns (contexts, ok) where contexts is a list of [l, q, s, r] and ok is
    False if a halting context would be required (or the seed is not closed).
    """
    table, _, _ = parse(tm)
    nq = len(table)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    work = list(contexts)
    while work:
        l, q, s, r = work.pop()
        if (l, q, s, r) in contexts and (l, q, s, r) == (0, 0, 0, 0):
            pass
        tr = table.get((q, s))
        if tr is None:
            return None, False  # halting context
        w, move, q2 = tr
        if move == 1:
            l2 = left[l][w] if l < len(left) else None
            if l2 is None:
                return None, False
            # for every (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                row = right[r2]
                for s2 in range(len(row)):
                    if row[s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            work.append(ctx)
        else:
            r2 = right[r][w] if r < len(right) else None
            if r2 is None:
                return None, False
            for l2 in range(len(left)):
                row = left[l2]
                for s2 in range(len(row)):
                    if row[s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            work.append(ctx)
    return contexts, True


def _prune(tm, left, right):
    """Keep only transitions actually used by the closure, remap states."""
    contexts, ok = _closure(tm, left, right, 0)
    if not ok:
        return None
    used_l = set()
    used_r = set()
    for l, q, s, r in contexts:
        used_l.add(l)
        used_r.add(r)
    if 0 not in used_l or 0 not in used_r:
        return None
    # remap
    remap_l = {}
    remap_r = {}
    for x in sorted(used_l):
        remap_l[x] = len(remap_l)
    for x in sorted(used_r):
        remap_r[x] = len(remap_r)
    nl = len(remap_l)
    nr = len(remap_r)
    new_left = [[None] * 2 for _ in range(nl)]
    new_right = [[None] * 2 for _ in range(nr)]
    new_left[0][0] = 0
    new_right[0][0] = 0
    for l in used_l:
        for x in range(2):
            tgt = left[l][x]
            if tgt is not None and tgt in remap_l:
                new_left[remap_l[l]][x] = remap_l[tgt]
    for r in used_r:
        for x in range(2):
            tgt = right[r][x]
            if tgt is not None and tgt in remap_r:
                new_right[remap_r[r]][x] = remap_r[tgt]
    new_ctx = [[remap_l[l], q, s, remap_r[r]] for l, q, s, r in contexts]
    return {"kind": "cps", "left": new_left, "right": new_right,
            "contexts": new_ctx}


def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    n = n_states
    # Try one half-tape tables of size 1, 2, 3 (state 0 loops on 0)
    for size in (1, 2, 3):
        for left in _build_tables(size, 2):
            # mirror: same table for the other side
            cert = _prune(tm, left, left)
            if cert is not None:
                try:
                    check(tm, cert)
                except Reject:
                    continue
                return cert
    return None
