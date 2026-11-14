import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------------------------------------------------------------------------
# decider "tcycle_probe"
#
# The surviving holdouts are all machines that look exactly like the ones in
# the samples: a small "crawler" that writes a 1, walks away, bounces off the
# right end, comes back over the written region, and the whole pattern
# translates one cell per lap while growing / keeping a periodic window.
# Such behaviour is a translated cycle (kind "tcycle").  A naive cycle search
# from a fixed T misses it because the state repeats only after a full lap
# (P steps) and the tape is then shifted by d != 0.
#
# Strategy: for a fixed starting time T (one lap is complete), let P grow and
# test the *invariant* form directly:
#     (a) state at T+P must equal state at T,
#     (b) the window [lo, hi] read during the lap must be reproduced shifted
#         by d = displacement of the head over the lap,
#     (c) cells outside the window on the far side must be blank.
# We do this without the kernel first, cheaply, then hand the certificate to
# `check` before returning it.  We try all T in a bounded range and all P up
# to a bound (the kernel allows t+p <= 100000).
# ---------------------------------------------------------------------------

def _window_shift_ok(tape_a, lo, hi, d):
    # tape_a: dict pos->sym at time T.  We already have the algorithm checked
    # below; this helper is only used to avoid re-implementing twice.
    return None

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # A translated cycle needs at least one full lap; sample the first phase
    # first to find the size of the lap.  We simulate a generous horizon.
    HMAX = 40000          # horizon for simulation
    LAPS = 60             # how many lap lengths we probe

    # Simulate once, recording (state, pos, tape) snapshots at each step.
    # We cap the amount of memory by only keeping what we need: the snapshot
    # at every step in the first HMAX steps is fine (40000 steps).
    steps = HMAX
    snap_state = []
    snap_pos = []
    snap_tape = []
    try:
        # run() gives us the final tape only; to get snapshots we simulate
        # ourselves using the parsed table.
        from neverhalt.tm import parse as _p
        # Re-implement a tiny simulator that yields snapshots.
        tape = {}
        state = 0
        pos = 0
        snap_state.append(state)
        snap_pos.append(pos)
        snap_tape.append(dict(tape))
        halted = False
        n = 0
        while n < HMAX:
            key = (state, tape.get(pos, 0))
            if key not in table:
                halted = True
                break
            w, mv, ns = table[key]
            if w:
                tape[pos] = w
            else:
                tape.pop(pos, None)
            pos = pos + mv
            state = ns
            n += 1
            snap_state.append(state)
            snap_pos.append(pos)
            snap_tape.append(dict(tape))
        if halted:
            return None
    except Exception:
        return None

    # Try to find a translated cycle: for each T in a small set of "lap
    # boundaries" and each P (a multiple of the lap), test the invariant.
    max_T = min(len(snap_state) - 1, HMAX)
    max_P = min(len(snap_state) - 1, HMAX)

    # Build a list of candidate T values: every step where the head is at a
    # local minimum (a bounce point), plus a range of early times.
    cand_T = []
    for t in range(0, max_T + 1):
        cand_T.append(t)

    # To keep runtime sane, sample T sparsely first, then densely if needed.
    import math
    def test_cycle(T, P):
        if T + P >= len(snap_state):
            return None
        st_a = snap_state[T]
        st_b = snap_state[T + P]
        if st_a != st_b:
            return None
        pa = snap_pos[T]
        pb = snap_pos[T + P]
        d = pb - pa
        # Head positions seen during the lap.
        lo = min(snap_pos[T:T + P + 1])
        hi = max(snap_pos[T:T + P + 1])
        if d == 0:
            # Plain cycle: window content must be unchanged.
            ta = snap_tape[T]
            tb = snap_tape[T + P]
            for y in range(lo, hi + 1):
                if ta.get(y, 0) != tb.get(y, 0):
                    return None
            # Verify with the kernel.
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                return None
        else:
            # Translated cycle: content shifted by d.
            ta = snap_tape[T]
            tb = snap_tape[T + P]
            for y in range(lo, hi + 1):
                if ta.get(y, 0) != tb.get(y + d, 0):
                    return None
            if d > 0:
                # Every cell right of hi must be blank at T+P.
                for y in range(hi + 1, hi + d + 1):
                    if tb.get(y, 0) != 0:
                        return None
            else:
                for y in range(lo + d, lo):
                    if tb.get(y, 0) != 0:
                        return None
            cert = {"kind": "cycle", "t": T, "p": P}
            try:
                check(tm, cert)
                return cert
            except Reject:
                return None

    # First pass: coarse scan over T and P.
    step_T = 1
    step_P = 1
    if max_T > 3000:
        step_T = max(1, max_T // 1500)
    if max_P > 3000:
        step_P = max(1, max_P // 1500)

    for T in range(0, max_T + 1, step_T):
        # P must be at least a few steps; try a geometric-ish set of P.
        Ps = []
        P = 1
        while P <= max_P - T:
            Ps.append(P)
            P = P * 2 if P < 64 else P + 64
        for P in Ps:
            r = test_cycle(T, P)
            if r is not None:
                return r

    # Second pass: dense scan if the coarse one found nothing.
    for T in range(0, max_T + 1):
        for P in range(1, max_P - T + 1):
            r = test_cycle(T, P)
            if r is not None:
                return r

    return None


def _unused():
    pass
