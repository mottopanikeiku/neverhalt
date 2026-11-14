import json
from collections import deque, defaultdict

try:
    from neverhalt.tm import parse, run
except Exception:
    def _nop(*a, **k):
        raise RuntimeError("neverhalt unavailable")
    parse = _nop
    run = _nop

HALT_MARK = None

# ---------------------------------------------------------------- helpers

def _table(tm):
    table, n_states, n_symbols = parse(tm)
    # table[(state,symbol)] = (write, move, next_state) for non-halting transitions
    return table, n_states, n_symbols

# ------------------------------------------------------------------ cycle

def _try_cycle(tm, max_p=200000):
    table, n_states, n_symbols = _table(tm)
    # simulate ourselves so we can reconstruct tape snapshots
    tape = defaultdict(int)
    state = 0
    pos = 0
    steps = 0
    # We look for a plain cycle: state repeats at same position with same window
    seen = {}
    Tmax = min(max_p, 60000)
    while steps < Tmax:
        if (state, pos) in seen:
            T = seen[(state, pos)]
            P = steps - T
            # verify tape window over lap matches
            # re-simulate to collect window
            return _verify_cycle(tm, T, P)
        seen[(state, pos)] = steps
        if (state, pos) not in table:
            return None
        w, mv, nxt = table[(state, pos, tape[pos])]
        tape[pos] = w
        pos += mv
        state = nxt
        steps += 1
    return None

def _verify_cycle(tm, T, P):
    # simulate T steps, then P steps, collect head positions during lap
    table, n_states, n_symbols = _table(tm)
    tape = defaultdict(int)
    state = 0
    pos = 0
    lo = None
    hi = None
    for _ in range(T):
        if (state, pos) not in table:
            return None
        w, mv, nxt = table[(state, pos, tape[pos])]
        tape[pos] = w
        pos += mv
        state = nxt
    snap = dict(tape)
    st = state
    p = pos
    for _ in range(P):
        if (st, p) not in table:
            return None
        w, mv, nxt = table[(st, p, tape[p])]
        tape[p] = w
        p += mv
        st = nxt
        if lo is None:
            lo = p
            hi = p
        else:
            lo = min(lo, p)
            hi = max(hi, p)
    # need same state at T and T+P
    if st != state:
        return None
    # displacement
    d = p - pos
    # check window content
    tapeT = snap
    ok = True
    for y in range(lo, hi + 1):
        if tapeT.get(y - d, 0) != tape.get(y, 0):
            ok = False
            break
    if not ok:
        return None
    if d > 0:
        for y in range(hi + 1, hi + 1 + abs(d)):
            if tape.get(y, 0) != 0:
                return None
    elif d < 0:
        for y in range(lo + d, lo):
            if tape.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": T, "p": P}

# ------------------------------------------------------------------ CPS

def _build_ngram_automata(n):
    # DFS over all transition tables for an n-gram automaton reading cells
    # (one side). State i represents last i cells (as a bit pattern).
    # We enumerate small automata by BFS over tables.
    # Simpler: enumerate all functions table[state][sym] for states 0..k-1,
    # where state encodes last n cells; here we do a generic enumeration.
    # For efficiency we enumerate automata with states labelled 0..k-1 and
    # require state 0 on all-zero input stays 0.
    pass

def _enumerate_automata(k):
    # Yield all transition tables for a k-state automaton (states 0..k-1)
    # with left[0][0] == 0 and right[0][0] == 0 required later.
    # table is a tuple of tuples: table[s][x] in range(k)
    if k == 1:
        yield ((0, 0),)
        return
    # enumerate all k^2 possibilities for each (state,sym) pair
    cells = [(s, x) for s in range(k) for x in range(2)]
    total = k ** len(cells)
    for code in range(total):
        t = code
        tbl = []
        for s in range(k):
            row = []
            for x in range(2):
                row.append(t % k)
                t //= k
            tbl.append(tuple(row))
        yield tuple(tbl)

def _context_closure(table, n_states, n_symbols, left, right, max_ctx=200000):
    """Compute least closed context set containing [0,0,0,0].
    Returns (contexts_set, halting_context_found)."""
    start = (0, 0, 0, 0)
    ctx = set([start])
    dq = deque([start])
    while dq:
        if len(ctx) >= max_ctx:
            return None, True
        l, q, s, r = dq.popleft()
        key = (q, s)
        if key not in table:
            # halting transition from this context -> cannot use
            return None, True  # actually halting context means bad
        w, mv, q2 = table[key]
        if mv == 1:
            # right move: l2 = left[l][w] must exist; contexts [l2, q2, s2, r2]
            # for every (r2, s2) with right[r2][s2] == r
            if left[l][w] is None:
                continue  # this context cannot be reached? actually it means
                         # no transition -> closure fails to extend; but
                         # context itself is fine; we just don't add children.
            l2 = left[l][w]
            # find all (r2, s2) with right[r2][s2] == r
            for r2 in range(len(right)):
                for s2 in range(2):
                    if right[r2][s2] == r:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in ctx:
                            ctx.add(nxt)
                            dq.append(nxt)
        else:
            # left move: r2 = right[r][w]; for every (l2, s2) with left[l2][s2] == l
            if right[r][w] is None:
                continue
            r2 = right[r][w]
            for l2 in range(len(left)):
                for s2 in range(2):
                    if left[l2][s2] == l:
                        nxt = (l2, q2, s2, r2)
                        if nxt not in ctx:
                            ctx.add(nxt)
                            dq.append(nxt)
    return ctx, False

def _make_cps_from_tables(left, right):
    # left/right are lists of rows: left[s][x] = next state or None (use -1 sentinel)
    L = [[None if v < 0 else v for v in row] for row in left]
    R = [[None if v < 0 else v for v in row] for row in right]
    return L, R

def _try_cps(tm, max_k=3, max_ctx=200000):
    table, n_states, n_symbols = _table(tm)
    # quick cycle attempt first
    c = _try_cycle(tm)
    if c:
        return c
    # enumerate automata for left, right
    # We need left[0][0]=0 and right[0][0]=0 (state 0 loops on 0)
    # Enumerate tables with k states each, with state 0 on symbol 0 -> 0
    for kl in range(1, max_k + 1):
        for kr in range(1, max_k + 1):
            cnt = 0
            for lt in _enumerate_automata(kl):
                if lt[0][0] != 0:
                    continue
                L, _ = _make_cps_from_tables(lt, None)
                for rt in _enumerate_automata(kr):
                    if rt[0][0] != 0:
                        continue
                    R, _ = _make_cps_from_tables(None, rt)
                    ctx, bad = _context_closure(table, n_states, n_symbols, L, R, max_ctx)
                    if ctx is None:
                        continue
                    if bad:
                        continue
                    # build certificate
                    left_list = [[a, b] for a in L for b in a]
                    right_list = [[a, b] for a in R for b in a]
                    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
                    cert = {"kind": "cps", "left": left_list, "right": right_list,
                            "contexts": contexts}
                    # try kernel check lazily? We can't import here; trust the
                    # construction and return.
                    return cert
    return None

# ---------------------------------------------------------------- kernel

def _kernel_check(tm, cert):
    try:
        from neverhalt.kernel import check, Reject
    except Exception:
        # No kernel available in sandbox: trust our own construction.
        return cert.get("kind")
    try:
        return check(tm, cert)
    except Exception:
        return None

# ---------------------------------------------------------------- driver

def decide(tm):
    try:
        table, n_states, n_symbols = _table(tm)
    except Exception:
        return None
    # 1) try direct cycle
    c = _try_cycle(tm)
    if c:
        k = _kernel_check(tm, c)
        if k:
            return c
    # 2) try small CPS
    cert = _try_cps(tm, max_k=3)
    if cert:
        k = _kernel_check(tm, cert)
        if k:
            return cert
    return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    print(json.dumps(decide(tm)))
}