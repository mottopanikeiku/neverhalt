import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _build_left_table(m, n, extra):
    """Deterministic automaton over one half-tape side.

    State 0 is the all-blank state and must loop on symbol 0.  States
    1..n are arbitrary; we enumerate extra transitions only, the rest
    are null (never happens) so the closure stays small.
    """
    tbl = [[None, None] for _ in range(n + 1)]
    tbl[0][0] = 0
    for st in range(1, n + 1):
        for sym in (0, 1):
            tbl[st][sym] = None
    idx = 0
    for st in range(1, n + 1):
        for sym in (0, 1):
            if idx >= len(extra):
                return None
            tbl[st][sym] = extra[idx]
            idx += 1
    return tbl


def _contexts_left_automaton(tbl, q, s, w, move, q2):
    """For a left move: r2 = right[r][w] must exist and for every pair
    (l2, s2) with left[l2][s2] == l we need [l2, q2, s2, r2] present.

    We enumerate candidate contexts and close them.  This helper returns
    the list of new contexts implied by one step, given the current
    context set as a set of tuples.
    """
    out = []
    for (l, qq, ss, r) in current:
        a = tbl[l][ss]
        if a is None:
            continue
        # move is +1 (right move): push w onto left half-tape
        l2 = tbl[l][w]
        if l2 is None:
            continue
        for (r2, s2) in right_pairs:
            if (l2, q2, s2, r2) not in current:
                out.append((l2, q2, s2, r2))
    return out


def _closure(table, n_states, n_symbols):
    """Closed context set for the given machine table.

    table[(q, s)] = (w, move, q2) or absent (halts).
    Returns a dict with kind, left, right, contexts or None.
    """
    # --- enumerate deterministic automata for one side ---
    # state 0 loops on 0; enumerate 1..n states with all transitions,
    # canonical: state ids assigned in BFS order from 0.
    # BFS-canonical enumeration of DFAs with at most `max_states` states.
    max_states = 4
    # We enumerate transition tables for the LEFT automaton only and let
    # the right automaton be its reverse-determinization (far-to-head),
    # which the kernel reads as the "right" table.
    # Enumerate all partial DFAs with states 0..k-1, 0 loops on 0.
    # To keep it tiny, enumerate tables where each state has at most one
    # non-null transition and all non-null transitions go to lower or
    # equal ids (a canonical form that still covers many counters).
    # ------------------------------------------------------------------
    # This is a placeholder skeleton; the real decider below does the
    # actual per-machine search.  The kernel is authoritative: only
    # certificates that pass check() are returned.
    pass


def decide(tm):
    try:
        table, ns, ncol = parse(tm)
    except Exception:
        return None
    # --- first pass: translated-cycle scan ---
    # Look for a lap of length P ending in the same state with a
    # constant displacement d, and a window that repeats shifted by d.
    halted, steps, state, pos, tape = run(tm, 3000)
    if halted:
        return None
    # Re-run and record the trajectory.
    try:
        tr = _trajectory(tm, 3000)
    except Exception:
        return None
    if tr is None:
        return None
    # Search for a translated cycle: T and T+P with same state, d>0,
    # window [lo,hi] content matching shifted by d, right side blank.
    for T in range(0, len(tr) - 1):
        qT, pT, tT = tr[T]
        for P in range(1, 400):
            if T + P >= len(tr):
                break
            qP, pP, tP = tr[T + P]
            if qT != qP:
                continue
            d = pP - pT
            if d == 0:
                continue
            lo = min(p for (_, p, _) in tr[T:T + P + 1])
            hi = max(p for (_, p, _) in tr[T:T + P + 1])
            if d > 0:
                if hi + d >= len(tT):
                    continue
                ok = all(tP.get(y + d, 0) == tT.get(y, 0) for y in range(lo, hi + 1))
                if not ok:
                    continue
                # right of hi blank at T+P
                blank = all(y not in tP or tP[y] == 0 for y in range(hi + 1, len(tP)))
                if not blank:
                    continue
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Exception:
                    pass
    # --- second pass: small-automaton CPS search ---
    try:
        cert = _search_cps(tm, table, ns, ncol)
    except Exception:
        cert = None
    return cert


def _trajectory(tm, max_steps):
    """Record (state, pos, tape_snapshot) for max_steps steps."""
    from neverhalt.tm import run
    # run() gives only the final tape; we need snapshots.  Re-simulate
    # step by step using parse directly.
    table, ns, ncol = parse(tm)
    q = 0
    p = 0
    tape = {}
    tr = []
    for _ in range(max_steps):
        tr.append((q, p, dict(tape)))
        key = (q, tape.get(p, 0))
        if key not in table:
            return tr
        w, mv, q2 = table[key]
        tape[p] = w
        p += 1 if mv > 0 else -1
        q = q2
    tr.append((q, p, dict(tape)))
    return tr


def _search_cps(tm, table, ns, ncol):
    """Search small deterministic automata for the left half-tape and
    reverse-determinize for the right half-tape, then close contexts."""
    q0 = 0
    # Build the context closure for a pair of automata.
    # Automaton for left: reads cells left of head far->head.
    # Automaton for right: reads cells right of head far->head.
    # We enumerate DFAs for the left side with 1..3 states; the right
    # side is the reverse-determinization of the left language (mirror
    # of the same counter/bouncer), which is a DFA we build directly.
    for nleft in (1, 2, 3):
        for nright in (1, 2, 3):
            ltab = _enum_dfa(nleft)
            rtab = _enum_dfa(nright)
            for lt in ltab:
                for rt in rtab:
                    cert = _close(tm, table, ns, ncol, lt, rt)
                    if cert is not None:
                        return cert
    return None


def _enum_dfa(n):
    """All deterministic automata with n states (0..n-1), state 0 loops
    on 0, other transitions arbitrary, canonical BFS order from 0."""
    if n == 1:
        return [[[0, 0]]]
    out = []
    # enumerate all transition tables
    choices = [(i, s, j) for i in range(n) for s in (0, 1) for j in range(n)]
    # fix state 0 on symbol 0 -> 0
    import itertools
    other = [(i, s) for i in range(1, n) for s in (0, 1)]
    for combo in itertools.product(range(n), repeat=len(other)):
        tbl = [[None, None] for _ in range(n)]
        tbl[0][0] = 0
        for (i, s), j in zip(other, combo):
            tbl[i][s] = j
        out.append(tbl)
        if len(out) > 4000:
            break
    return out


def _close(tm, table, ns, ncol, lt, rt):
    """Compute the closed context set for automata lt (left) and rt
    (right) and return the certificate if no halting context exists."""
    # contexts as tuples (l, q, s, r)
    ctx = {(0, 0, 0, 0)}
    frontier = list(ctx)
    # right pairs: (r2, s2) with rt[r2][s2] == r  -- but the kernel's
    # condition is stated the other way: for a right move, l2 = lt[l][w]
    # and [l2, q2, s2, r2] must be a context for EVERY pair (r2, s2)
    # with rt[r2][s2] == r.  We collect all (r2, s2) pairs by scanning
    # the right table.
    right_pairs = {}
    for r2 in range(len(rt)):
        for s2 in (0, 1):
            if rt[r2][s2] is not None:
                right_pairs.setdefault(rt[r2][s2], []).append((r2, s2))
    left_pairs = {}
    for l2 in range(len(lt)):
        for s2 in (0, 1):
            if lt[l2][s2] is not None:
                left_pairs.setdefault(lt[l2][s2], []).append((l2, s2))
    # iterate
    while frontier:
        new = []
        for (l, q, s, r) in frontier:
            key = (q, s)
            if key not in table:
                # halting context: reject
                return None
            w, mv, q2 = table[key]
            if mv > 0:
                l2 = lt[l][w]
                if l2 is None:
                    return None
                for (r2, s2) in right_pairs.get(r, []):
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        new.append(c)
            else:
                r2 = rt[r][w]
                if r2 is None:
                    return None
                for (l2, s2) in left_pairs.get(l, []):
                    c = (l2, q2, s2, r2)
                    if c not in ctx:
                        ctx.add(c)
                        new.append(c)
        frontier = new
        if len(ctx) > 200000:
            return None
    # build certificate
    left = [[lt[i][0], lt[i][1]] for i in range(len(lt))]
    right = [[rt[i][0], rt[i][1]] for i in range(len(rt))]
    contexts = [[l, q, s, r] for (l, q, s, r) in ctx]
    cert = {"kind": "cps", "left": left, "right": right, "contexts": contexts}
    try:
        from neverhalt.kernel import check
        check(tm, cert)
        return cert
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    tm = sys.argv[1]
    print(decide(tm))
