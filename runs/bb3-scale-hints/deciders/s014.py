NAME = "small_automata_search"

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _transitions(tm):
    table, ns, nsym = parse(tm)
    out = []
    for q in range(ns):
        row = []
        for s in range(nsym):
            if (q, s) in table:
                w, mv, q2 = table[(q, s)]
                row.append((w, mv, q2))
            else:
                row.append(None)
        out.append(row)
    return out, ns, nsym


def _build_left(t):
    """Build the left-reading automaton for the given transition table.

    left[i][x] = state reached from state i on symbol x, or None.
    State 0 is the all-blank half-tape: left[0][0] == 0.
    We enumerate small DFAs with states 0..n-1.  Symbol 0 loops at 0.
    """
    out = []
    for i in range(len(t)):
        row = []
        for x in range(2):
            if i == 0 and x == 0:
                row.append(0)
            else:
                row.append(None)
        out.append(row)
    return out


def _enumerate_automata(n_states, seed=None):
    """Yield every DFA transition table with states 0..n_states-1.

    Symbol 0 at state 0 is fixed to 0.  All other entries range over
    {0, ..., n_states-1} (None not needed here: the kernel's `left` and
    `right` tables must be total for the states that are reachable; we
    only emit the transitions the closure actually used).
    """
    fixed = []
    free = []
    for i in range(n_states):
        for x in range(2):
            if i == 0 and x == 0:
                fixed.append(0)
            else:
                free.append(i * 2 + x)
    import itertools
    for combo in itertools.product(range(n_states), repeat=len(free)):
        table = [[None, None] for _ in range(n_states)]
        table[0][0] = 0
        idx = 0
        for i in range(n_states):
            for x in range(2):
                if i == 0 and x == 0:
                    continue
                table[i][x] = combo[idx]
                idx += 1
        yield table


def _closure(t, ns, nsym, left, right):
    """Compute the smallest closed context set for the given pair.

    Returns (contexts, ok) where contexts is a list of [l, q, s, r] and ok
    is False if a halting context was found (or a None was needed).
    """
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            if s >= nsym:
                return None, False
            tr = t[q][s]
            if tr is None:
                return None, False  # halting context
            w, mv, q2 = tr
            if mv == 1:  # right move
                l2 = left[l][w] if l < len(left) and w < len(left[l]) else None
                if l2 is None:
                    return None, False
                for r2 in range(len(right)):
                    for s2 in range(nsym):
                        if right[r2][s2] == r:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                nxt.append(ctx)
            else:  # left move
                r2 = right[r][w] if r < len(right) and w < len(right[r]) else None
                if r2 is None:
                    return None, False
                for l2 in range(len(left)):
                    for s2 in range(nsym):
                        if left[l2][s2] == l:
                            ctx = (l2, q2, s2, r2)
                            if ctx not in contexts:
                                contexts.add(ctx)
                                nxt.append(ctx)
        frontier = nxt
    return contexts, True


def _emit(tm, left, right, contexts):
    """Emit the certificate.  Keep only the transitions actually used."""
    used_l = set()
    used_r = set()
    for (l, q, s, r) in contexts:
        used_l.add(l)
        used_r.add(r)
    # Prune: drop rows/cols not reachable from state 0.
    def prune(table, used):
        keep = set()
        stack = [0]
        while stack:
            i = stack.pop()
            if i in keep:
                continue
            keep.add(i)
            for x in range(len(table[i])):
                if table[i][x] is not None and table[i][x] not in keep:
                    stack.append(table[i][x])
        new = []
        remap = {}
        for i in range(len(table)):
            if i not in keep:
                continue
            remap[i] = len(new)
            new.append([table[i][0], table[i][1]])
        # Remap indices.
        for row in new:
            for x in range(2):
                if row[x] is not None:
                    row[x] = remap[row[x]]
        return new, remap

    left2, rmap = prune(left, used_l)
    right2, lmap = prune(right, used_r)
    # Remap context indices.
    ctx = []
    for (l, q, s, r) in contexts:
        l2 = rmap.get(l)
        r2 = lmap.get(r)
        if l2 is None or r2 is None:
            return None
        ctx.append([l2, q, s, r2])
    cert = {
        "kind": "cps",
        "left": [[a if a is not None else None for a in row] for row in left2],
        "right": [[a if a is not None else None for a in row] for row in right2],
        "contexts": ctx,
    }
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm):
    t, ns, nsym = _transitions(tm)
    # Quick reject: if the machine halts in a short simulation, skip.
    halted, steps, _, _, _ = run(tm, 200)
    if halted:
        return None
    # Try 1-state automata first.
    for n in (1, 2, 3):
        for left in _enumerate_automata(n):
            for right in _enumerate_automata(n):
                contexts, ok = _closure(t, ns, nsym, left, right)
                if not ok:
                    continue
                cert = _emit(tm, left, right, contexts)
                if cert is not None:
                    return cert
    return None
