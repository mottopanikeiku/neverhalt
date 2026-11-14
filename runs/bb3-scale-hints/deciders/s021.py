from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def decide(tm):
    tm = tm.rstrip()
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None

    # --- Part 1: cycle / translated cycle search over a bounded window. ---
    for maxlap in (64, 256, 1024, 4096, 16384, 65536):
        try:
            res = _find_cycle(tm, table, ns, maxlap)
        except Exception:
            res = None
        if res is not None:
            return res

    # --- Part 2: CPS with small automata enumerated from scratch. ---
    try:
        cert = _cps_search(tm, table, ns)
    except Exception:
        cert = None
    if cert is not None:
        return cert

    return None


def _find_cycle(tm, table, ns, maxlap):
    """Look for a repeated configuration (T, state, pos) and then verify the
    window invariance by simulation. Returns a cycle certificate or None."""
    seen = {}
    state = 0
    pos = 0
    tape = {}
    step = 0
    limit = 200000
    # Store positions of (state,pos) -> step where first seen; also store tape.
    # To keep memory bounded, only remember recent checkpoints.
    checkpoints = {}
    T = None
    P = None
    while step < limit:
        key = (state, pos)
        if key in checkpoints:
            T = checkpoints[key]
            P = step - T
            if P <= maxlap:
                break
        else:
            if len(checkpoints) > 60000:
                # drop oldest
                k = next(iter(checkpoints))
                del checkpoints[k]
            checkpoints[key] = step
        # step
        if (state, tape.get(pos, 0)) not in table:
            return None
        w, mv, nstate = table[(state, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        pos += mv
        state = nstate
        step += 1
    if T is None or P is None:
        return None
    # Verify by re-simulating and checking window invariance.
    try:
        return _verify_cycle(tm, T, P)
    except Exception:
        return None


def _verify_cycle(tm, T, P):
    # Simulate T+P steps, snapshot tape and head positions during the lap.
    state = 0
    pos = 0
    tape = {}
    step = 0
    snapshot_T = None
    lap_positions = []
    while step < T + P:
        if step == T:
            snapshot_T = dict(tape)
            lap_positions = []
        if (state, tape.get(pos, 0)) not in table_global[tm_key[0]]:
            return None
        w, mv, nstate = table_global[tm_key[0]][(state, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        lap_positions.append(pos)
        pos += mv
        state = nstate
        step += 1
    # state at T+P same as at T?
    # We need state at T and at T+P. Recompute.
    state = 0
    pos = 0
    tape = {}
    step = 0
    state_T = None
    pos_T = None
    while step < T + P:
        if step == T:
            state_T = state
            pos_T = pos
        if (state, tape.get(pos, 0)) not in table_global[tm_key[0]]:
            return None
        w, mv, nstate = table_global[tm_key[0]][(state, tape.get(pos, 0))]
        if w:
            tape[pos] = w
        pos += mv
        state = nstate
        step += 1
    if state != state_T:
        return None
    d = pos - pos_T
    lo = min(lap_positions)
    hi = max(lap_positions)
    # check window content invariance
    for y in range(lo, hi + 1):
        v1 = snapshot_T.get(y, 0)
        v2 = tape.get(y + d, 0)
        if v1 != v2:
            return None
    # far side blank
    if d > 0:
        for y in range(hi + 1, hi + d + 1):
            if tape.get(y, 0) != 0:
                return None
    elif d < 0:
        for y in range(lo + d, lo):
            if tape.get(y, 0) != 0:
                return None
    return {"kind": "cycle", "t": T, "p": P}


# module-level caches (reset per decide call is fine since we run one machine)
tm_key = [None]
table_global = [None]


def _reset(tm, table):
    tm_key[0] = tm
    table_global[0] = table


# --- CPS with enumeration of small automata for each half-tape ---

def _cps_search(tm, table, ns):
    _reset(tm, table)
    # Determine halting transitions: states/symbols not in table.
    halt_pairs = set()
    for q in range(ns):
        for s in (0, 1):
            if (q, s) not in table:
                halt_pairs.add((q, s))
    if not halt_pairs:
        return None

    # We need to find two DFAs L and R (each with state 0 = blank half-tape loop on 0)
    # such that the context closure starting from (0,0,0,0) contains no halting context.
    # Enumerate automata by size 1,2,3,... up to ~4 states. For each pair, compute
    # closure and check.
    for nl in range(1, 5):
        for nr in range(1, 5):
            for L in _enum_automata(nl):
                for R in _enum_automata(nr):
                    cert = _closure(L, R, ns, table, halt_pairs)
                    if cert is not None:
                        return cert
    return None


def _enum_automata(n):
    """Enumerate all deterministic automata with n states (states 0..n-1),
    where state 0 loops on symbol 0: L[0][0] == 0.
    Transitions on symbols 0 and 1 to any state, or None (dead)."""
    results = []
    # represent transitions as tuple of n pairs (t0, t1)
    # t_i in 0..n-1 or None
    vals = list(range(n)) + [None]
    def rec(i, acc):
        if i == n:
            results.append(tuple(acc))
            return
        for a in vals:
            for b in vals:
                acc.append((a, b))
                rec(i + 1, acc)
                acc.pop()
    rec(0, [])
    # filter: state 0 on symbol 0 must be 0
    out = []
    for t in results:
        if t[0][0] != 0:
            continue
        out.append(t)
    return out


def _closure(L, R, ns, table, halt_pairs):
    """Compute the smallest closed context set containing (0,0,0,0).
    L and R are tuples of transitions; L[q][s] is state or None.
    Returns a certificate dict or None."""
    # contexts: (l, q, s, r)
    start = (0, 0, 0, 0)
    seen = {start}
    stack = [start]
    contexts = []
    while stack:
        (l, q, s, r) = stack.pop()
        if (q, s) in halt_pairs:
            return None  # halting context: this pair fails
        if (q, s) not in table:
            return None
        w, mv, q2 = table[(q, s)]
        if mv > 0:
            # right move: l2 = L[l][w]
            if L[l][w] is None:
                return None
            l2 = L[l][w]
            # for every (r2, s2) with R[r2][s2] == r
            for r2 in range(len(R)):
                for s2 in (0, 1):
                    if R[r2][s2] == r:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
        else:
            # left move: r2 = R[r][w]
            if R[r][w] is None:
                return None
            r2 = R[r][w]
            for l2 in range(len(L)):
                for s2 in (0, 1):
                    if L[l2][s2] == l:
                        ctx = (l2, q2, s2, r2)
                        if ctx not in seen:
                            seen.add(ctx)
                            stack.append(ctx)
    if len(seen) > 200000:
        return None
    contexts = sorted(seen)
    left_tab = [[L[i][0], L[i][1]] for i in range(len(L))]
    right_tab = [[R[i][0], R[i][1]] for i in range(len(R))]
    return {
        "kind": "cps",
        "left": left_tab,
        "right": right_tab,
        "contexts": [[l, q, s, r] for (l, q, s, r) in contexts],
    }