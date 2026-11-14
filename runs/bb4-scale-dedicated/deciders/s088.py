from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

SYMS = (0, 1)


def _table_from_rows(rows):
    # rows: list of 2 ints; -1 = null
    return rows


def _compose_left(l, w):
    if w < 0 or w > 1:
        return None
    v = l[w]
    if v is None:
        return None
    return v


def _contexts_closed(left, right, n_states, n_ctx_limit=200000):
    """Compute the smallest closed context set for a pair (left, right).

    left[i][x] = state or None, right[i][x] = state or None.
    Context = (l, q, s, r).  Return list of contexts, or None if a halting
    transition is forced (i.e. closure requires a context whose transition
    halts).
    """
    # transitions of the machine are looked up by caller; here we do closure
    # with a supplied transition function.
    raise RuntimeError("unused")


def _closure(trans, left, right, max_ctx=200000):
    """trans(q, s) -> (w, move, q2) or None (halt).

    left/right: automaton tables (list of lists, entries None or int).
    Returns (contexts, ok) where contexts is a list of (l,q,s,r) and ok is
    False if the closure is forced to include a halting context.
    """
    start = (0, 0, 0, 0)
    seen = {start}
    frontier = [start]
    contexts = []
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            contexts.append((l, q, s, r))
            tr = trans(q, s)
            if tr is None:
                return contexts, False
            w, move, q2 = tr
            if move > 0:
                l2 = left[l][w]
                if l2 is None:
                    return contexts, False
                for s2 in SYMS:
                    r2 = right[r][s2]
                    if r2 is None:
                        continue
                    if right[r2][s2] == r:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            nxt.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return contexts, False
                for s2 in SYMS:
                    l2 = left[l][s2]
                    if l2 is None:
                        continue
                    if left[l2][s2] == l:
                        c = (l2, q2, s2, r2)
                        if c not in seen:
                            seen.add(c)
                            nxt.append(c)
        if len(contexts) > max_ctx:
            return contexts, False
        frontier = nxt
    return contexts, True


def _enumerate_tables(n_states, used_states, used_syms):
    """Enumerate canonical transition tables of size n_states x len(used_syms).

    State 0 must loop on symbol 0: table[0][0] == 0.
    Returns list of tables (list of lists of ints).
    """
    nsym = len(used_syms)
    total = (n_states + 1) ** nsym
    out = []
    for code in range(total):
        t = []
        x = code
        ok = True
        for i in range(n_states):
            row = []
            for j in range(nsym):
                row.append(x % (n_states + 1))
                x //= (n_states + 1)
            if i == 0 and j == 0 and row[0] != 0:
                ok = False
                break
            t.append(row)
        if not ok:
            continue
        out.append(t)
    return out


def _to_kernel_table(t):
    return [row[:] for row in t]


def _make_cert_contexts(contexts, left, right):
    """Convert internal contexts to kernel format.

    Kernel wants left and right as transition tables with null for missing.
    It wants contexts as [l, q, s, r].
    """
    L = []
    for row in left:
        L.append([v for v in row])
    R = []
    for row in right:
        R.append([v for v in row])
    return {
        "kind": "cps",
        "left": L,
        "right": R,
        "contexts": [list(c) for c in contexts],
    }


def _try_pair(tm, left, right):
    table, n_states, n_symbols = parse(tm)
    # Build transition function using parsed table.
    def trans(q, s):
        key = (q, s)
        if key not in table:
            return None
        w, move, q2 = table[key]
        return (w, move, q2)
    contexts, ok = _closure(trans, left, right)
    if not ok:
        return None
    cert = _make_cert_contexts(contexts, left, right)
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert


def decide(tm: str) -> dict | None:
    """Search over small CPS automata pairs (1..3 states per side)."""
    table, n_states, n_symbols = parse(tm)
    # Only symbols that actually appear in transitions matter, but keep 0,1.
    for n_left in (1, 2, 3):
        for n_right in (1, 2, 3):
            # Enumerate left tables with n_left states, right with n_right.
            # To keep search small, use canonical BFS order implicitly by
            # iterating codes; prune aggressively inside.
            left_tables = _enumerate_tables(n_left, set(range(n_left)), [0, 1])
            right_tables = _enumerate_tables(n_right, set(range(n_right)), [0, 1])
            for L in left_tables:
                for R in right_tables:
                    cert = _try_pair(tm, L, R)
                    if cert is not None:
                        return cert
    return None


if __name__ == "__main__":
    # quick self-test with a known non-halting machine if provided
    pass
