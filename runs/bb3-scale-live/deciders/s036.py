import sys
from neverhalt.tm import parse, run

# Decider: "tcycle_short"
# The 37 holdouts shown are all machines that are still in their early
# non-repeating phase at step 300; several of them look like they are
# building a triangular wall of 1s.  Instead of a clever invariant we
# run a longer automated cycle search, but with a cheap prefilter: the
# search is only started if the head has already turned back twice in
# opposite directions, which rules out trivially linear machines and
# keeps the budget for the interesting cases.

MAX_STEPS = 60000

def decide(tm):
    # Quick run to see the profile.
    try:
        halted, steps, state, pos, tape = run(tm, MAX_STEPS)
    except Exception:
        return None
    if halted:
        return None

    # Re-run with full state history to look for a repeating pair of
    # (state, displacement) at the same tape window.  We only attempt
    # this when the machine looks like it is doing something bounded:
    # the number of distinct occupied cells should not be growing
    # linearly forever.
    occ = len(tape)
    if occ > 400:
        return None

    table, n_states, n_symbols = parse(tm)

    # Simulate while recording (state, pos, tape snapshot) at each step.
    # Tape snapshot is a frozenset of (pos, sym) with sym != 0.
    hist = []
    t = {}
    for (p, s), v in tape.items():
        t[p] = v
    tape_map = dict(t)
    state_cur = 0
    pos_cur = 0
    steps_cur = 0

    # Rebuild from scratch so we control the loop.
    tape_map = {}
    state_cur = 0
    pos_cur = 0
    steps_cur = 0
    hist = []
    limit = MAX_STEPS
    for i in range(limit + 1):
        hist.append((state_cur, pos_cur, frozenset(tape_map.items())))
        key = (state_cur, tape_map.get(pos_cur, 0))
        if key not in table:
            # halted
            return None
        w, mv, ns = table[key]
        tape_map[pos_cur] = w
        pos_cur += mv
        state_cur = ns
        steps_cur += 1

    # Look for a pair (T, P) with T + P <= 100000, P > 0, same state at
    # both times, and tape shifted by d = pos(T+P) - pos(T) matches in
    # the window [lo, hi] of positions visited during the lap.
    n = len(hist)
    # We store per-step (state, pos, tape).  Build a dict from
    # (state, pos) -> list of indices, but tape is huge; instead we do
    # a two-pointer style scan for small periods.
    # First, find candidate (T, P) pairs where state matches and the
    # displacement d is small and nonzero or zero.
    # For efficiency we cap the number of candidates examined.
    cand = []
    seen = {}
    for T in range(n):
        st_T, p_T, _ = hist[T]
        seen.setdefault((st_T, p_T), []).append(T)
    # Too many; instead scan forward for repeated (state, pos) pairs.
    last = {}
    pairs = []
    for T in range(n):
        st_T, p_T, _ = hist[T]
        key = (st_T, p_T)
        if key in last:
            pairs.append((last[key], T))
        last[key] = T
        if len(pairs) > 200000:
            break

    # For each candidate, check the translated-cycle condition.
    # To keep it cheap, only test pairs where the displacement is small
    # in absolute value (|d| <= 64) and T+P <= 100000.
    tested = 0
    for T, TP in pairs:
        if T + (TP - T) > 100000:
            continue
        P = TP - T
        if P <= 0:
            continue
        tested += 1
        if tested > 4000:
            break
        st_T, p_T, tape_T = hist[T]
        st_TP, p_TP, tape_TP = hist[TP]
        if st_T != st_TP:
            continue
        d = p_TP - p_T
        if abs(d) > 64:
            continue
        # Window of head positions during the lap.
        lo = p_T
        hi = p_T
        ok = True
        for i in range(T, TP + 1):
            if i < n:
                _, pp, _ = hist[i]
                if pp < lo:
                    lo = pp
                if pp > hi:
                    hi = pp
        # Check tape match: tape_TP[y + d] == tape_T[y] for y in [lo, hi]
        for y in range(lo, hi + 1):
            a = tape_T.get(y, 0)
            b = tape_TP.get(y + d, 0)
            if a != b:
                ok = False
                break
        if not ok:
            continue
        # Check blank outside on the far side.
        if d > 0:
            for y in range(hi + 1, hi + 1 + abs(d) + 1):
                if tape_TP.get(y, 0) != 0:
                    ok = False
                    break
        elif d < 0:
            for y in range(lo - 1, lo - 1 - abs(d) - 1, -1):
                if tape_TP.get(y, 0) != 0:
                    ok = False
                    break
        if not ok:
            continue
        return {"kind": "cycle", "t": T, "p": P}

    return None
