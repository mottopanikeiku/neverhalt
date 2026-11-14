import sys
sys.setrecursionlimit(10000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# ---------- helpers ----------

def _steps_to(table, state, symbol, n_symbols):
    if (state, symbol) not in table:
        return None
    return table[(state, symbol)]

# ---------- decider ----------

NAME = "holdout_37_probe"

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # A cheap but broad attempt: run a long simulation and look for a
    # translated cycle (kind "tcycle"), i.e. a window whose content
    # repeats shifted by a constant head displacement.
    try:
        halted, steps, state, pos, tape = run(tm, 20000)
    except Exception:
        return None

    if halted:
        return None

    # Snapshot the head trace: (t, state, pos)
    try:
        table2, ns, nsym = parse(tm)
    except Exception:
        return None

    # Re-run while recording history; we stop early if we hit a halting step.
    state = 0
    pos = 0
    tape = {}
    hist = []  # (t, q, pos, dict_copy_of_tape)
    t = 0
    LIMIT = 20000
    while t < LIMIT:
        key = (state, tape.get(pos, 0))
        if key not in table2:
            return None  # halted; not our business
        w, mv, q2 = table2[key]
        tape[pos] = w
        pos += mv
        state = q2
        t += 1
        # record a snapshot every step is too costly; record every step anyway
        # for a short horizon, then thin out.  For 20000 steps the dict copy
        # is too heavy, so we instead record (t, state, pos) and reconstruct
        # the tape only for candidate windows.
        hist.append((t, state, pos))
        if len(hist) > LIMIT:
            break

    # Look for a translated cycle with small |d| and small period.
    # We compare a window of the tape at time T with the tape at time T+P
    # shifted by d = pos(T+P) - pos(T), for states matching.
    # To keep it cheap we only inspect a bounded window around the head.
    W = 40  # window half-width
    for P in range(1, min(len(hist) // 2, 4000)):
        # candidate T values: states must match
        # iterate T from 0..len(hist)-P-1 in steps, but that is O(n^2).
        # Instead index by (state) first.
        pass

    # Build index: for each state, list of times.
    by_state = {}
    for i, (tt, st, pp) in enumerate(hist):
        by_state.setdefault(st, []).append(i)

    # For speed, only consider P that divides differences frequently:
    # try every P in a modest set.
    maxT = len(hist)
    for P in range(1, min(maxT, 3000)):
        if maxT - P < 20:
            break
        # map time -> index
        # We compare T and T+P.  Precompute list of times for each state.
        # For efficiency, for each state st, get sorted list of times.
        # Then for each T in that list, check T+P is same state.
        for st, times in by_state.items():
            j = 0
            # two-pointer: find pairs (T, T+P) both in times
            import bisect
            for T in times:
                idx = bisect.bisect_left(times, T + P)
                if idx < len(times) and times[idx] == T + P:
                    Ti = T
                    Tj = T + P
                    if Tj >= maxT:
                        continue
                    # reconstruct tapes at Ti and Tj
                    # re-simulate is too slow; instead we stored only
                    # positions.  Reconstruct via a second pass is needed.
                    # To avoid that, we instead simulate a fresh run and
                    # snapshot the window around the head at the two times.
                    pass

    # Simpler and bounded approach: simulate once, storing a full tape
    # snapshot every K steps for a limited horizon, then test windows.
    K = 200
    snapshots = []  # (t, dict(tape), pos, state)
    state = 0
    pos = 0
    tape = {}
    t = 0
    while t < LIMIT:
        if t % K == 0:
            snapshots.append((t, dict(tape), pos, state))
        key = (state, tape.get(pos, 0))
        if key not in table2:
            return None
        w, mv, q2 = table2[key]
        tape[pos] = w
        pos += mv
        state = q2
        t += 1

    snapshots.append((t, dict(tape), pos, state))

    # Try to find translated cycles between snapshots with |d| small.
    n = len(snapshots)
    for i in range(n):
        ti, tapei, posi, sti = snapshots[i]
        for j in range(i + 1, n):
            tj, tapej, posj, stj = snapshots[j]
            if sti != stj:
                continue
            d = posj - posi
            if abs(d) > 200:
                continue
            # check window around head at tj compared to shifted window at ti
            lo = min(posi, posj) - W
            hi = max(posi, posj) + W
            ok = True
            for y in range(lo, hi + 1):
                # tape_tj[y + d] should equal tape_ti[y]
                if tapei.get(y, 0) != tapej.get(y + d, 0):
                    ok = False
                    break
            if not ok:
                continue
            # build a full certificate using run()
            T = ti
            P = tj - ti
            # verify with run to count steps and get exact state/pos/tape
            try:
                halted, steps, fstate, fpos, ftape = run(tm, T + P)
            except Exception:
                return None
            if halted:
                continue
            cert = {"kind": "tcycle", "t": T, "p": P, "d": d}
            try:
                from neverhalt.kernel import check, Reject
                kind = check(tm, cert)
                return cert
            except Reject:
                continue
            except Exception:
                return None
    return None