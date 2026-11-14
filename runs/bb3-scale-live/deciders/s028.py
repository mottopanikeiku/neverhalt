from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# The holdouts fall into a few families:
#   - machines that build a growing "staircase" / triangle of 1s and sweep back
#     and forth over it (the first three samples), a translated cycle in the
#     window of the sweep, or a context-closed set describing the sweep;
#   - machines that write an expanding periodic pattern of 1s and holes
#     (samples 4 and 5): a counter over the left half-tape plus a fixed
#     n-gram memory of the right half-tape closes them.
#
# Strategy: (a) translated-cycle search with an expanding window, which catches
# sweeps whose period is short and whose 'lap' is contained in a bounded
# window; (b) a context-closed-set search over the state space of "last n cells
# of each half-tape" (n-gram CPS), seeded with the all-blank context and closed
# under the transition relation, which catches periodic-pattern builders.
# Both are cheap to run and return a certificate only when the kernel can
# verify it, so a wrong guess is harmless.


def _halting(tm):
    # quick pre-check: if the machine halts within the simulation window the
    # decider should return None (there is nothing to prove).
    halted, steps, state, pos, tape = run(tm, 120)
    return halted


def _cycle_search(tm, max_t=4000, laps=3, window=60):
    """Look for a translated cycle: simulate T steps, then a lap of P steps,
    and require the lap to repeat with the same state and window content."""
    halted, steps, state, pos, tape = run(tm, max_t + window * laps + 10)
    if halted or steps < max_t:
        return None
    # positions relative to the head at time T
    head0 = pos
    # Re-simulate to record the head trajectory and tape at T and T+P.
    # We use run() twice with different limits to get the states at T and T+P.
    # First get the state/tape at time T.
    hT, stepsT, stateT, posT, tapeT = run(tm, max_t)
    if hT or stepsT < max_t:
        return None
    # record window content at T
    loT = posT - window
    hiT = posT + window
    winT = {}
    for y in range(loT, hiT + 1):
        winT[y] = tapeT.get(y, 0)
    # Now simulate P steps from T and check the lap condition.
    for P in range(1, window * laps + 1):
        hT2, stepsT2, stateT2, posT2, tapeT2 = run(tm, max_t + P)
        if hT2 or stepsT2 < max_t + P:
            return None
        if stateT2 != stateT:
            continue
        d = posT2 - posT
        # window seen during the lap: we approximate by checking a window of
        # size 2*window around both head positions.
        lo = min(posT, posT2) - window
        hi = max(posT, posT2) + window
        ok = True
        for y in range(lo, hi + 1):
            v1 = tapeT.get(y, 0)
            v2 = tapeT2.get(y + d, 0)
            if v1 != v2:
                ok = False
                break
        if not ok:
            continue
        # blank requirement on the far side
        if d > 0:
            for y in range(hiT + 1, hiT + abs(d) + 1):
                if tapeT2.get(y, 0) != 0:
                    ok = False
                    break
        elif d < 0:
            for y in range(loT - abs(d), loT):
                if tapeT2.get(y, 0) != 0:
                    ok = False
                    break
        if ok:
            cert = {"kind": "cycle", "t": max_t, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None


def _ngram_cps(tm, n=6, max_states=6000, max_contexts=200000):
    """Build a closed context set over 'last n cells of each half-tape'."""
    table, n_states, _ = parse(tm)
    # abstract automaton state = tuple of last n cells (far to near), or None
    # for 'all blank tail'.  We use integer encoding: 0 means all-blank tail.
    # state 0 is the all-blank half-tape.
    def enc(cells):
        # cells: tuple of length n, far to near, values 0/1
        v = 0
        for c in cells:
            v = (v << 1) | c
        return v
    # automaton transitions: from a tail encoding on reading a new cell (the
    # cell nearest the head) return the new tail encoding.
    # left automaton reads cells from far away towards the head, i.e. it
    # consumes the cell just written by a right move; the new cell is the
    # nearest one, so the tail shifts: new = (old << 1 | newcell) & mask.
    mask = (1 << n) - 1
    def step_auto(state, cell):
        if state == 0:
            # all blank tail; a 0 keeps it blank, a 1 starts a tail
            if cell == 0:
                return 0
            return 1
        return ((state << 1) | cell) & mask
    # Build the set of reachable contexts by closure.
    # context = (l, q, s, r)
    contexts = set()
    contexts.add((0, 0, 0, 0))
    frontier = [(0, 0, 0, 0)]
    # precompute automaton transitions lazily
    auto_cache = {}
    def auto(state, cell):
        key = (state, cell)
        if key not in auto_cache:
            auto_cache[key] = step_auto(state, cell)
        return auto_cache[key]
    while frontier:
        newf = []
        for (l, q, s, r) in frontier:
            if q >= n_states:
                continue
            tr = table.get((q, s))
            if tr is None:
                continue  # halting transition: this context is not added
            w, move, q2 = tr
            if move > 0:
                # right move: push w onto left half-tape
                l2 = auto(l, w)
                if l2 is None:
                    continue
                # pop the nearest cell from the right half-tape.  Every
                # possible symbol s2 that could lead to state r:
                for s2 in (0, 1):
                    # find all r2 with auto(r2, s2) == r; we approximate by
                    # enumerating reachable r2 values.
                    pass
                # enumerate r2 candidates from the set of states we know
                cand_r2 = set()
                for (l3, q3, s3, r3) in contexts:
                    if auto(r3, s2) == r:
                        cand_r2.add(r3)
                # also try to discover new r2 by simulating: for each possible
                # tail state r2 consistent with the current r after reading s2
                for r2 in list(cand_r2):
                    ctx = (l2, q2, s2, r2)
                    if ctx not in contexts:
                        contexts.add(ctx)
                        newf.append(ctx)
            else:
                r2 = auto(r, w)
                if r2 is None:
                    continue
                cand_l2 = set()
                for (l3, q3, s3, r3) in contexts:
                    if auto(l3, s3) == l:
                        cand_l2.add(l3)
                for l2c in list(cand_l2):
                    for s2 in (0, 1):
                        ctx = (l2c, q2, s2, r2)
                        if ctx not in contexts:
                            contexts.add(ctx)
                            newf.append(ctx)
        frontier = newf
        if len(contexts) > max_contexts:
            return None
    if (0, 0, 0, 0) not in contexts:
        return None
    # verify closure fully and build the certificate
    left_rows = []
    right_rows = []
    # collect all automaton states used
    lstates = set()
    rstates = set()
    for (l, q, s, r) in contexts:
        lstates.add(l)
        rstates.add(r)
    lmax = max(lstates) if lstates else 0
    rmax = max(rstates) if rstates else 0
    for i in range(lmax + 1):
        row = []
        for x in (0, 1):
            row.append(auto(i, x))
        left_rows.append(row)
    for i in range(rmax + 1):
        row = []
        for x in (0, 1):
            row.append(auto(i, x))
        right_rows.append(row)
    ctx_list = [[l, q, s, r] for (l, q, s, r) in contexts]
    cert = {"kind": "cps", "left": left_rows, "right": right_rows,
            "contexts": ctx_list}
    try:
        check(tm, cert)
        return cert
    except Reject:
        return None


def decide(tm: str):
    if _halting(tm):
        return None
    c = _cycle_search(tm)
    if c is not None:
        return c
    for n in (3, 4, 5, 6, 7, 8):
        c = _ngram_cps(tm, n=n)
        if c is not None:
            return c
    return None