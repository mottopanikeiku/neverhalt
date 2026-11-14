from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "two or three words"
# Strategy: run each machine for a long time and look for periodic head/state
# behavior over a moving window, then certify with a translated cycle.
# Additionally, try to detect a translated cycle directly from the trace by
# looking for repeated (state, head displacement) pairs at a fixed offset.

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Simulate a long trace, but bounded by the kernel limit t+p <= 100000.
    # We track the head position and state at each step.
    # tape is a dict pos -> symbol (0 or 1), blank = 0.
    # We'll implement our own trace to capture the head position at each step.

    # Reconstruct the machine semantics from the table.
    # table[(state, symbol)] = (write, move, next_state) where move is +1 or -1.
    # States are ints, A = 0. Halting transition absent from table.
    # Start: state A (0), position 0, tape all zeros.

    def trace(max_steps):
        # returns list of (step, state, pos, tape) where tape is dict pos->sym (non-zero)
        state = 0
        pos = 0
        tape = {}
        steps = []
        for t in range(max_steps + 1):
            steps.append((t, state, pos, dict(tape)))
            if (state, tape.get(pos, 0)) not in table:
                # halted
                return steps, True
            w, mv, nxt = table[(state, tape.get(pos, 0))]
            tape[pos] = w
            pos += mv
            state = nxt
        return steps, False

    # Try to find a translated cycle: look for two times T < T+P with same state
    # and same local tape pattern shifted by d = pos(T+P) - pos(T).
    # We'll scan a trace and compare windows.

    # First run a long trace (up to some limit) to gather data.
    MAX = 60000
    steps, halted = trace(MAX)
    if halted:
        return None  # it halts, not our concern (we only prove non-halting)

    # We'll try to find a repeated state with the same tape window shifted.
    # Use a dictionary keyed by (state, displacement, window bytes) but that's heavy.
    # Instead, look for repeated (state, pos) pairs; if the same state appears at
    # positions with the same displacement, check the tape.

    # Collect snapshots: at each step, record state and pos.
    # We'll look for pairs (T, T+P) with same state and same displacement d.
    # Then compare the window of cells around the head.

    # To limit memory, we only keep state and pos, and rebuild tape as needed.
    # Actually we have the full tape dict at each step in `steps`, which is heavy.
    # Let's redo with a lighter trace: only state, pos, and a hash of local window.

    # We'll re-simulate to get the trace with local window hashes.
    # Window: cells from pos-20 to pos+20, as a tuple of symbols.

    def light_trace(max_steps, W=30):
        state = 0
        pos = 0
        tape = {}
        rec = []
        for t in range(max_steps + 1):
            # window hash: read cells around pos
            lo = pos - W
            hi = pos + W
            win = tuple(tape.get(x, 0) for x in range(lo, hi + 1))
            rec.append((t, state, pos, win))
            if (state, tape.get(pos, 0)) not in table:
                return rec, True
            w, mv, nxt = table[(state, tape.get(pos, 0))]
            tape[pos] = w
            pos += mv
            state = nxt
        return rec, False

    rec, halted = light_trace(MAX)
    if halted:
        return None

    # Look for a translated cycle: same state, same window shifted by d.
    # For each pair (i, j) with j > i, if state_i == state_j and
    #   win_i shifted by (pos_j - pos_i) matches win_j over the overlap,
    #   and the non-overlapping part is blank.
    # We'll search for j - i = P and d = pos_j - pos_i.
    # To keep it fast, index by state.

    from collections import defaultdict
    by_state = defaultdict(list)
    for idx, (t, st, p, win) in enumerate(rec):
        by_state[st].append(idx)

    # Try to find a candidate: for each state, look at occurrences.
    # We'll do a limited search: for each i, for each j in same state with j-i <= 5000.
    # Check window match with shift d = pos_j - pos_i.

    def check_window_match(i, j, W=30):
        t_i, st_i, p_i, win_i = rec[i]
        t_j, st_j, p_j, win_j = rec[j]
        if st_i != st_j:
            return None
        d = p_j - p_i
        # win covers positions p_i - W .. p_i + W (in terms of indices in win)
        # win_j covers p_j - W .. p_j + W.
        # We need win_j[y + d] == win_i[y] for y in overlap, and the rest blank.
        # Overlap: y such that p_i - W + y is in [p_j - W, p_j + W] and also in win_i range.
        # Since win_i is indexed by absolute pos - (p_i - W), index k corresponds to pos p_i - W + k.
        # win_j index k corresponds to pos p_j - W + k.
        # We need for every cell y in [lo, hi] (head positions seen during lap) ...
        # Actually the kernel certificate requires specific T, P, and then it verifies.
        # We can just try to construct the certificate and call check.
        # But we need a valid T, P, and the kernel will simulate and verify.
        # So we can just try many (T, P) pairs and call check.
        # However, check is expensive (simulates T+P steps). We want to limit calls.
        # So first do a quick local check to filter.

        # Quick check: compare the window that will be used by the kernel.
        # The kernel simulates T steps, then P more. It uses the head positions during
        # the lap to define [lo, hi]. We don't know them exactly without simulating.
        # Instead, we can just simulate T+P steps ourselves and check the condition.
        # But that's what the kernel does. To avoid many kernel calls, we do a cheap
        # necessary condition: the state at T and T+P must be same, and the tape
        # displacement d must satisfy that the window content matches.
        # We'll just use the rec data: compare win_i and win_j with shift d.
        # The window in rec is centered at pos. The kernel uses the head positions
        # during the lap. Our window is a superset. If our window matches, likely good.
        # Let's require that win_j and win_i match under shift d over the full window
        # where both are defined, and that the parts that go out of the window are blank.
        # win_i has indices 0..2W, corresponding to positions p_i - W + k.
        # win_j indices 0..2W, positions p_j - W + k.
        # Condition: for all k in 0..2W, let y = p_i - W + k. If y is in the range of win_j,
        #   i.e., p_j - W <= y <= p_j + W, then win_j[y - (p_j - W)] == win_i[k].
        # And cells outside win_j that are read (i.e., y < p_j - W or y > p_j + W) must be blank.
        # Actually the kernel checks: tape_{T+P}[y + d] == tape_T[y] for every y in [lo, hi],
        # and when d > 0, every cell right of hi is blank at T+P.
        # This is a local condition. Our window check is a good filter.
        # Let's just require that win_i and win_j are identical under shift d over the
        # overlapping region, and that the non-overlapping part is all zeros.
        # We'll compute the overlap.
        # Positions: win_i covers [p_i - W, p_i + W]. win_j covers [p_j - W, p_j + W].
        # Shift d = p_j - p_i. We need win_j[y + d] == win_i[y] for y in [lo, hi].
        # The kernel uses [lo, hi] = head positions during lap. That's a subset of
        # the union of windows. For a quick filter, we can check the entire window
        # that is within both: y in [max(p_i - W, p_j - W - d), min(p_i + W, p_j + W - d)].
        # Actually simpler: check that for all y in [p_i - W, p_i + W],
        #   if y + d is in [p_j - W, p_j + W], then win_j[y + d - (p_j - W)] == win_i[y - (p_i - W)].
        # And for y in [p_i - W, p_i + W] with y + d outside [p_j - W, p_j + W],
        #   win_i[...] must be 0 (blank) because it's outside the window at T+P.
        # Wait, the kernel condition: tape_{T+P}[y + d] == tape_T[y] for y in [lo, hi].
        # This means for every y in the window, the cell at y+d in T+P must match
        # the cell at y in T. If y+d is outside our captured window at T+P, we need
        # it to be blank (since tape is mostly blank). So we require win_i to be 0
        # for those y where y+d is outside [p_j - W, p_j + W].
        # This is a necessary condition for the kernel to accept (with our window).
        # Let's implement.

        for k in range(2 * W + 1):
            y = p_i - W + k
            val = win_i[k]
            y2 = y + d
            # y2 in win_j range?
            if p_j - W <= y2 <= p_j + W:
                if win_j[y2 - (p_j - W)] != val:
                    return False
            else:
                # must be blank at T+P, so val must be 0
                if val != 0:
                    return False
        return True

    # Search for a candidate (i, j) with same state and window match.
    # We'll limit the number of kernel calls by only trying a few candidates.
    candidates = []
    for st, occ in by_state.items():
        # occ is list of indices sorted
        for a in range(len(occ)):
            i = occ[a]
            for b in range(a + 1, len(occ)):
                j = occ[b]
                if j - i > 5000:
                    break
                if check_window_match(i, j):
                    candidates.append((i, j))
                    if len(candidates) >= 50:
                        break
            if len(candidates) >= 50:
                break
        if len(candidates) >= 50:
            break

    # Try to get certificates for the candidates.
    for i, j in candidates:
        T = rec[i][0]
        P = rec[j][0] - rec[i][0]
        if T + P > 100000:
            continue
        cert = {"kind": "cycle", "t": T, "p": P}
        try:
            check(tm, cert)
            return cert
        except Reject:
            continue
        except Exception:
            continue
    return None
} 