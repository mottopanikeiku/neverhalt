from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# We look for cycles by exhaustive search over a fixed window of steps.
# The remaining holdouts drift: the head marches in one direction, leaving
# a repeating pattern of blank cells behind, while a "bouncer" walks back
# and forth ahead of the wave.  A translated cycle whose lap is a multiple
# of the wave period fits that picture, but the lap window must be large
# enough to cover the full spatial period.


def _try_lap(tm, max_steps=40000):
    """Search for a translated or ordinary cycle by brute force.

    We simulate once up to max_steps, recording the full history of
    (state, position, tape contents in the visited range) at every step.
    Then for each candidate lap start T we look for a later step T+P with
    the same state, same window content shifted by d, and the right outside
    blankness.  We only need to remember the window between the minimum and
    maximum head position seen so far, plus a little margin.
    """
    halted, steps, state, pos, tape = run(tm, max_steps)
    if halted:
        return None
    # Re-simulate but storing per-step (state, pos, tape copy restricted to
    # the currently visited interval).  Storing everything is too big, so
    # store the tape as a dict snapshot every step but only for positions
    # that are non-zero or within a small radius of the head.
    table, _, _ = parse(tm)
    n_states = max(s for _, s in table) + 1
    tape = {}
    pos = 0
    st = 0
    hist = []  # list of (state, pos, frozenset of (cell,tape) in [pos-64, pos+64])
    for step in range(max_steps):
        if (st, tape.get(pos, 0)) not in table:
            break
        w, move, st2 = table[(st, tape.get(pos, 0))]
        tape[pos] = w
        pos += move
        st = st2
        lo = pos - 64
        hi = pos + 64
        snap = frozenset((y, tape[y]) for y in range(lo, hi + 1) if y in tape)
        hist.append((st, pos, snap))
    # Search for a lap T -> T+P.
    n = len(hist)
    # Limit P to something reasonable; the machines in the sample have
    # periods that look small (the patterns repeat every few steps).
    for T in range(n):
        st0, pos0, snap0 = hist[T]
        # quick index by state
        for P in range(1, min(2000, n - T)):
            st1, pos1, snap1 = hist[T + P]
            if st1 != st0:
                continue
            d = pos1 - pos0
            # window [lo, hi] = positions seen during the lap.  We only have
            # a 64-cell radius snapshot; that is enough if the lap is short.
            lo = pos0 - 64
            hi = pos0 + 64
            ok = True
            for y in range(lo, hi + 1):
                if snap1.get(y + d) != snap0.get(y):
                    # need to compare the actual tape values, not just the
                    # restricted snapshots.  Recompute from snapshots: the
                    # snapshot at T+P contains values for positions
                    # [pos1-64, pos1+64]; if y+d falls outside, it is blank
                    # unless it is in snap1.
                    if (y + d, 0) in snap1 or y + d not in range(pos1 - 64, pos1 + 65):
                        pass
                    v1 = snap1.get(y + d, (y + d, 0))[1] if (y + d, 0) in snap1 else (0 if (y + d) not in snap1 and pos1 - 64 <= y + d <= pos1 + 64 else None)
                    v0 = snap0.get(y, (y, 0))[1] if (y, 0) in snap0 else (0 if pos0 - 64 <= y <= pos0 + 64 else None)
                    if v0 != v1:
                        ok = False
                        break
            if not ok:
                continue
            # outside blankness: every cell right of hi must be blank at T+P
            # (for d>0).  We approximate using the snapshot range.
            if d > 0:
                for y in range(hi + 1, pos1 + 64 + 1):
                    if y in snap1:
                        ok = False
                        break
                if ok:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
            elif d < 0:
                for y in range(pos1 - 64 - 1, lo - 1, -1):
                    if y in snap1:
                        ok = False
                        break
                if ok:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
            else:
                if ok:
                    cert = {"kind": "cycle", "t": T, "p": P}
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None


def decide(tm: str):
    return _try_lap(tm, max_steps=40000)