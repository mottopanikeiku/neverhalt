from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def _bg(tm):
    # Bounded-but-large search for a translated cycle: try a window of
    # recent configurations and look for a repeat after a nonzero shift.
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    n_states = 3
    # Simulate up to a decent horizon, tracking head position and a
    # coarse tape hash to find candidate repeat times.
    max_steps = 4000
    try:
        halted, steps, state, pos, tape = run(tm, max_steps)
    except Exception:
        return None
    if halted:
        return None
    # Re-simulate while recording configurations enough to detect a
    # translated-cycle. Use a concrete simulation loop with history.
    try:
        table, ns, nsym = parse(tm)
    except Exception:
        return None
    # Reconstruct simulation manually to record history.
    tape = {}
    head = 0
    state = 0
    hist = []  # (state, pos, frozenset(tape.items()))
    for step in range(max_steps + 1):
        hist.append((state, head, frozenset(tape.items())))
        tr = table.get((state, tape.get(head, 0)))
        if tr is None:
            break
        w, mv, q2 = tr
        tape[head] = w
        head += mv
        state = q2
    # Search for translated cycles: compare configuration at time T and
    # T+P with a shift d. Approximate by looking for a repeated pair
    # (state, shifted tape window). We'll do a targeted scan: for each
    # P in a set of plausible laps, compare (state, pos, tape-window).
    def window_at(idx, lo, hi):
        # tape window relative to head
        s, p, t = hist[idx]
        return (s, tuple((y, t.get(y, 0)) for y in range(p + lo, p + hi + 1)))
    # Try to find any T, P, d such that a translated cycle certificate
    # verifies. We'll brute-force over a modest horizon and a small set
    # of shifts.
    horizon = min(len(hist) - 1, 600)
    # Precompute head positions and tape snapshots compactly.
    for T in range(0, horizon):
        sT, pT, tT = hist[T]
        for P in range(1, min(horizon - T, 300) + 1):
            # Quick check: same state
            s2, p2, t2 = hist[T + P]
            if s2 != sT:
                continue
            d = p2 - pT
            if d == 0:
                continue
            # Candidate window: positions read in the lap
            lo = min(hist[i][1] for i in range(T, T + P + 1)) - pT
            hi = max(hist[i][1] for i in range(T, T + P + 1)) - pT
            # Verify shift condition approximately using actual tapes
            ok = True
            for y in range(lo, hi + 1):
                a = tT.get(pT + y, 0)
                b = t2.get(p2 + y, 0)
                if a != b:
                    ok = False
                    break
            if not ok:
                continue
            # Check boundary blank condition
            if d > 0:
                b_ok = all(t2.get(x, 0) == 0 for x in range(p2 + hi + 1, p2 + hi + 1 + d))
            else:
                b_ok = all(t2.get(x, 0) == 0 for x in range(p2 + lo + d, p2 + lo))
            if not b_ok:
                continue
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                continue
    return None

def decide(tm: str):
    try:
        return _bg(tm)
    except Exception:
        return None
