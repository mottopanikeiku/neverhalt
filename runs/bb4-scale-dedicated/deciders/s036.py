from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

try:
    from neverhalt.tm import parse as _parse
except Exception:
    _parse = parse


def _halt_states(tm):
    """Return the set of (state, symbol) pairs whose transition halts."""
    table, n_states, n_symbols = parse(tm)
    halting = set()
    for q in range(n_states):
        for s in range(n_symbols):
            if (q, s) not in table:
                halting.add((q, s))
    return table, n_states, n_symbols, halting


def _build_left_table(n_states_side):
    """Enumerate all left-automaton transition tables.

    left[i][x] = state reached from i on symbol x, or None if never.
    State 0 loops on symbol 0 (blank far away).
    """
    from itertools import product
    out = []
    # each row is a tuple of outputs for symbol 0 and 1
    rows = []
    for r in product(range(n_states_side + 1), repeat=2):
        rows.append(r)
    for combo in product(rows, repeat=n_states_side):
        left = [[combo[i][0], combo[i][1]] for i in range(n_states_side)]
        # state 0 must loop on symbol 0
        if left[0][0] != 0:
            continue
        out.append((tuple(tuple(r) for r in left), left))
    return out


def _build_right_table(n_states_side):
    """Enumerate right-automaton tables; state 0 loops on symbol 0."""
    return _build_left_table(n_states_side)


def _closure(tm, left, right):
    """Compute the smallest closed context set.

    Context = (l, q, s, r).  Start from (0, 0, 0, 0).  A context is closed
    when for every step the successor contexts are all present.

    Returns (contexts, ok) where ok is False if a halting context was forced.
    """
    table, n_states, n_symbols, halting = _halt_states(tm)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    stack = [(0, 0, 0, 0)]
    n_left = len(left)
    n_right = len(right)
    while stack:
        (l, q, s, r) = stack.pop()
        if (l, q, s, r) in contexts:
            if (q, s) in halting:
                return None, False
            continue
        contexts.add((l, q, s, r))
        stack.append((l, q, s, r))
        # step
        if (q, s) not in table:
            return None, False
        (w, move, q2) = table[(q, s)]
        if move == +1:
            # right move: l2 = left[l][w] must exist
            l2 = left[l][w]
            if l2 is None:
                return None, False
            # r2, s2 with right[r2][s2] == r
            succ = []
            for r2 in range(n_right):
                for s2 in range(n_symbols):
                    if right[r2][s2] == r:
                        succ.append((l2, q2, s2, r2))
            for c in succ:
                if c not in contexts:
                    stack.append(c)
        else:
            # left move: r2 = right[r][w] must exist
            r2 = right[r][w]
            if r2 is None:
                return None, False
            succ = []
            for l2 in range(n_left):
                for s2 in range(n_symbols):
                    if left[l2][s2] == l:
                        succ.append((l2, q2, s2, r2))
            for c in succ:
                if c not in contexts:
                    stack.append(c)
    return contexts, True


def _emit(tm, left, right, contexts):
    """Emit the certificate, keeping only used transitions."""
    left_out = []
    used_left = set()
    used_right = set()
    for (l, q, s, r) in contexts:
        used_left.add(l)
        used_right.add(r)
    n_left = len(left)
    n_right = len(right)
    for i in range(n_left):
        row = []
        for x in range(2):
            if i in used_left and left[i][x] is not None:
                row.append([left[i][x]])
            else:
                row.append(None)
        # the kernel expects a 2-element list [a, b] per row
        left_out.append([row[0], row[1]])
    right_out = []
    for i in range(n_right):
        row = []
        for x in range(2):
            if i in used_right and right[i][x] is not None:
                row.append([right[i][x]])
            else:
                row.append(None)
        right_out.append([row[0], row[1]])
    ctx_out = [[l, q, s, r] for (l, q, s, r) in contexts]
    return {"kind": "cps", "left": left_out, "right": right_out, "contexts": ctx_out}


def decide(tm: str):
    try:
        table, n_states, n_symbols, halting = _halt_states(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None
    # limit context count
    ctx_limit = 200000
    for n_side in range(1, 4):
        # enumerate left then right
        for lt, left in _build_left_table(n_side):
            # quick check: state 0 must be reachable
            for rt, right in _build_right_table(n_side):
                ctx, ok = _closure(tm, left, right)
                if ctx is None or not ok:
                    continue
                if len(ctx) > ctx_limit:
                    continue
                cert = _emit(tm, left, right, ctx)
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Exception:
                    continue
    return None
