import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# --- helpers ---------------------------------------------------------------

def _parse(tm):
    table, n_states, n_symbols = parse(tm)
    return table, n_states, n_symbols

def _step(table, state, sym):
    """Return (write, move, next) or None if halting."""
    try:
        w, mv, nxt = table[(state, sym)]
    except KeyError:
        return None
    return w, mv, nxt

def _run_to(tm, T):
    table, n_states, n_symbols = _parse(tm)
    tape = {0: 0}
    state = 0
    pos = 0
    for _ in range(T):
        s = tape.get(pos, 0)
        r = _step(table, state, s)
        if r is None:
            return None
        w, mv, nxt = r
        tape[pos] = w
        pos += mv
        state = nxt
    return (state, pos, dict(tape))

def _find_cycle(tm, max_t=4000, max_p=200):
    """Try a translated cycle certificate.  Returns dict or None."""
    table, n_states, n_symbols = _parse(tm)
    tape = {0: 0}
    state = 0
    pos = 0
    max_steps = max_t + max_p
    for T in range(0, max_steps):
        if T == max_t:
            # record snapshot at T
            snap_state = state
            snap_pos = pos
            snap_tape = dict(tape)
            break
        s = tape.get(pos, 0)
        r = _step(table, state, s)
        if r is None:
            return None
        w, mv, nxt = r
        tape[pos] = w
        pos += mv
        state = nxt
    else:
        return None
    # lap
    d = 0
    lo = snap_pos
    hi = snap_pos
    for _ in range(max_p):
        s = tape.get(pos, 0)
        r = _step(table, state, s)
        if r is None:
            return None
        w, mv, nxt = r
        tape[pos] = w
        pos += mv
        d += mv
        lo = min(lo, pos)
        hi = max(hi, pos)
        state = nxt
    if state != snap_state:
        return None
    if d == 0:
        return None
    # verify tape shift over [lo,hi]
    for y in range(lo, hi + 1):
        if tape.get(y + d, 0) != snap_tape.get(y, 0):
            return None
    if d > 0:
        for y in range(hi + 1, hi + 1 + abs(d) + 1):
            if tape.get(y, 0) != 0:
                return None
    else:
        for y in range(lo - 1 - abs(d), lo):
            if tape.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": snap_pos and 0 or 0, "p": max_p}

# --- DFA enumeration -------------------------------------------------------

def _enumerate_dfa_tables(k, max_states=3):
    """Enumerate transition tables with 1..max_states states.
    state 0 loops on symbol 0.
    Each row is a tuple (t0, t1) with values in range(k) or None.
    Yields (k, table) where table[i] = (row0, row1).
    """
    import itertools
    vals = list(range(k)) + [None]
    for n in range(1, max_states + 1):
        # canonical: state 0 row0 == 0
        for combo in itertools.product(vals, repeat=2 * n):
            table = [combo[2 * i:2 * i + 2] for i in range(n)]
            if table[0][0] != 0:
                continue
            yield table

# --- closed contexts -------------------------------------------------------

def _closed_contexts(tm, left, right, max_ctx=200000):
    table, n_states, n_symbols = _parse(tm)
    # contexts as (l, q, s, r)
    ctx = set()
    ctx.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    while frontier:
        nxt = []
        for (l, q, s, r) in frontier:
            res = _step(table, q, s)
            if res is None:
                return None  # halting context -> reject
            w, mv, q2 = res
            if mv == 1:
                # right move: push w onto left, pop from right
                l2 = left[l][w]
                if l2 is None:
                    return None
                # find r2, s2 with right[r2][s2] == r
                for (rr, ss) in _right_pairs(right, r):
                    c = (l2, q2, ss, rr)
                    if c not in ctx and len(ctx) + len(nxt) < max_ctx:
                        ctx.add(c)
                        nxt.append(c)
            else:
                r2 = right[r][w]
                if r2 is None:
                    return None
                for (ll, ss) in _left_pairs(left, l):
                    c = (ll, q2, ss, r2)
                    if c not in ctx and len(ctx) + len(nxt) < max_ctx:
                        ctx.add(c)
                        nxt.append(c)
        frontier = nxt
        if len(ctx) > max_ctx:
            return None
    return ctx

def _right_pairs(right, r):
    out = []
    for i, row in enumerate(right):
        for x, v in enumerate(row):
            if v == r:
                out.append((i, x))
    return out

def _left_pairs(left, l):
    out = []
    for i, row in enumerate(left):
        for x, v in enumerate(row):
            if v == l:
                out.append((i, x))
    return out

# --- main decider ----------------------------------------------------------

def decide(tm):
    try:
        table, n_states, n_symbols = _parse(tm)
    except Exception:
        return None
    # quick translated-cycle attempt
    try:
        c = _find_cycle(tm, max_t=3000, max_p=100)
        if c is not None:
            try:
                check(tm, c)
                return c
            except Reject:
                pass
    except Exception:
        pass
    # CPS with small DFA enumeration
    max_states = 3
    for k in (2, 3):
        for lf in _enumerate_dfa_tables(k, max_states):
            # require state 0 row0 == 0 already
            for rf in _enumerate_dfa_tables(k, max_states):
                # convert to list of lists for kernel
                L = [list(row) for row in lf]
                R = [list(row) for row in rf]
                try:
                    ctx = _closed_contexts(tm, L, R)
                except Exception:
                    continue
                if ctx is None:
                    continue
                left_list = [[a, b] for (a, b) in lf]
                right_list = [[a, b] for (a, b) in rf]
                contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                cert = {
                    "kind": "cps",
                    "left": left_list,
                    "right": right_list,
                    "contexts": contexts,
                }
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
    return None

if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        line = line.strip()
        if line:
            print(decide(line))
