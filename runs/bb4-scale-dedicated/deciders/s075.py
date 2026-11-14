import itertools

from neverhalt.kernel import Reject, check
from neverhalt.tm import parse, run

# ------------------------------------------------------------ helpers

def _parse(tm):
    table, ns, ny = parse(tm)
    return table, ns


def _run(tm, steps):
    return run(tm, steps)


def _halt_set(tm):
    table, ns = _parse(tm)
    return set(), ns


def _trans(tm, q, s):
    # q, s are 0-based ints; return (w, move, q2) or None
    table, ns = _parse(tm)
    t = table.get((q, s))
    if t is None:
        return None
    w, move, q2 = t
    return (w, move, q2)


# ------------------------------------------------------------ DFA search

def _dfa_search(tm, max_states=10, time_budget=3):
    """Enumerate far-to-head DFAs in BFS order, growing sizes 1..max_states.

    Returns a list of canonical transition tables (list of rows, row is a
    list of target indices or None).  A table of size k is canonical when
    only states reachable from state 0 are used and the states are BFS
    numbered, so each countable DFA appears once.
    """
    table, ns = _parse(tm)
    out = []
    for k in range(1, max_states + 1):
        if _all_k_canonical(tm, k, k, out):
            break
    return out


def _all_k_canonical(tm, k, budget, out):
    table, ns = _parse(tm)
    symbols = (0, 1)
    count = 0
    # enumerate canonical tables via BFS reachable states
    # state 0 is start; we choose targets among 0..k-1; states not
    # reachable from 0 are forbidden by canonicality, so enumerate only
    # trees of reachability.
    def rec(used, depth, rows):
        nonlocal count
        if count > budget:
            return
        if len(used) > k:
            return
        # rows: list of (r, c, target) chosen so far
        # completeness: every state in used must have both entries set
        pending = [state for state in used
                   if rows.get((state, 0), None) is None or
                   rows.get((state, 1), None) is None]
        if not pending:
            # build full table, canonicalise reachability
            reach = {0}
            frontier = [0]
            while frontier:
                nxt = []
                for st in frontier:
                    for c in symbols:
                        tgt = rows.get((st, c))
                        if tgt is not None and tgt not in reach:
                            reach.add(tgt)
                            nxt.append(tgt)
                frontier = nxt
            if reach == set(range(k)):
                # canonical BFS numbering
                order = [0]
                seen = {0}
                while len(order) < len(reach):
                    st = order[len(order) - 1]
                    for c in symbols:
                        tgt = rows.get((st, c))
                        if tgt is not None and tgt not in seen:
                            seen.add(tgt)
                            order.append(tgt)
                    if st is not None:
                        pass
                if len(order) < len(reach):
                    return
                remap = {old: new for new, old in enumerate(order)}
                newrows = []
                for st in range(k):
                    row = []
                    for c in symbols:
                        tgt = rows.get((st, c))
                        row.append(None if tgt is None else remap[tgt])
                    newrows.append(row)
                key = tuple(tuple(r) for r in newrows)
                if key not in out:
                    out.append(key)
            count += 1
            return
        st = pending[0]
        # branch on targets for this state's missing entries
        for c in symbols:
            if rows.get((st, c), None) is None:
                targets = list(used) + [len(used)]
                for tgt in targets:
                    rows2 = dict(rows)
                    rows2[(st, c)] = tgt
                    rec(used | ({tgt} if tgt not in used else used),
                        depth + 1, rows2)
        # also allow leaving the entry null (a dead transition)
        rows2 = dict(rows)
        rec(used, depth + 1, rows2)

    rec({0}, 0, {})
    return out


# ------------------------------------------------------------ context closure

def _closure(tm, left, right, limit=200000):
    table, ns = _parse(tm)
    # context = (l, q, s, r); q in range(ns), s in (0,1)
    # entries are canonical rows already, but convert to list-of-lists
    L = [list(row) for row in left]
    R = [list(row) for row in right]
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    while stack and len(seen) <= limit:
        (l, q, s, r) = stack.pop()
        t = table.get((q, s))
        if t is None:
            # halting context: the certificate cannot cover it, so the
            # closure is not halting-free
            return None
        w, move, q2 = t
        if move == 1:
            l2 = L[l][w] if w < len(L[l]) else None
            if l2 is None:
                return None
            for r2 in range(len(R)):
                for s2 in (0, 1):
                    if R[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            r2 = R[r][w] if w < len(R[r]) else None
            if r2 is None:
                return None
            for l2 in range(len(L)):
                for s2 in (0, 1):
                    if L[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    if len(seen) > limit:
        return None
    return sorted(seen)


def _emit(tm, left, right, contexts):
    L = [list(row) for row in left]
    R = [list(row) for row in right]
    # encode nulls as null
    left_out = [[None if v is None else int(v) for v in row] for row in L]
    right_out = [[None if v is None else int(v) for v in row] for row in R]
    ctx_out = [[int(l), int(q), int(s), int(r)] for (l, q, s, r) in contexts]
    return {"kind": "cps",
            "left": left_out,
            "right": right_out,
            "contexts": ctx_out}


# ------------------------------------------------------------ main

def decide(tm):
    try:
        table, ns = _parse(tm)
    except Exception:
        return None

    # Quick cycle check first (cheap and catches fixed points).
    try:
        for T in range(0, 200, 10):
            for P in range(10, 200 - T, 10):
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
    except Exception:
        pass

    try:
        do, _, _, _, _ = _run(tm, 600)
        if do:
            return None
    except Exception:
        return None

    # Search DFAs for the right half-tape, then build the left half-tape
    # automaton as the same table (the closure only needs the language).
    for left in _dfa_search(tm, max_states=6, budget=40):
        for right in _dfa_search(tm, max_states=6, budget=40):
            ctx = _closure(tm, left, right)
            if ctx is not None:
                cert = _emit(tm, left, right, ctx)
                try:
                    check(tm, cert)
                except Reject:
                    continue
                return cert
    return None


NAME = "dfa-search-cps"