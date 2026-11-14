from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: translated-cycle ("tcycle") detector.
# A translated cycle is a periodic pattern that moves across the tape and is
# proven by the kernel with the "cycle" certificate (d != 0 is reported as a
# tcycle by the kernel).  We search for a pair of times (T, T+P) with the same
# state, a nonzero head displacement d over the lap, and tape contents shifted
# by d, matching on the window [lo, hi] and blank outside on the entering side.
# We simulate up to LIM steps while remembering tape snapshots at every step,
# then test all pairs (T, T+P) whose states match.  This is the generic
# fallback that catches machines whose periodic laps are longer than the
# n-gram CPS window.

def decide(tm: str) -> dict | None:
    table, n_states, n_symbols = parse(tm)
    LIM = 100000
    # run step by step, recording (state, pos) and a tape snapshot
    halted, steps, state, pos, tape = run(tm, 0)
    if halted:
        return None
    # We re-simulate ourselves to snapshot every step.
    t, s, p = 0, 0, 0
    tape = {}
    snaps = []  # (state, pos, dict(tape))
    # initial step 0 snapshot
    snaps.append((s, p, dict(tape)))
    cur = tm
    # use run with max_steps=1 repeatedly? too slow. Implement our own step.
    # table[(state, symbol)] = (write, move, next_state); absent => halt.
    # move is +1 or -1
    def step(state, pos, tape):
        sym = tape.get(pos, 0)
        key = (state, sym)
        if key not in table:
            return None
        w, mv, ns = table[key]
        tape[pos] = w
        return ns, pos + mv
    # step 0 is the initial configuration (before any transition)
    # simulate
    for _ in range(LIM):
        r = step(s, p, tape)
        if r is None:
            return None
        s, p = r
        t += 1
        snaps.append((s, p, dict(tape)))
    n = len(snaps)
    # index by state for T
    # For each T, look forward for T+P with same state and nonzero displacement
    # and check the translated-cycle condition.
    # displacement d = p2 - p1 over the lap
    # [lo, hi] = head positions seen during the lap = min/max pos in [T, T+P]
    # condition: tape_{T+P}[y + d] == tape_T[y] for every y in [lo, hi]
    # and for d > 0 every cell right of hi is blank at T+P (d < 0: left of lo)
    # Note kernel also requires same state at T and T+P.
    # We search P from 1 upward, but cap work: for each T try P up to 20000.
    # To keep within time, sample T values and P range.
    # Full pair search is O(n^2); instead index by (state) lists.
    from collections import defaultdict
    by_state = defaultdict(list)
    for i in range(n):
        st, pp, _ = snaps[i]
        by_state[st].append(i)
    # try P values that are multiples of small periods first
    import math
    # candidate P list: 1..3000 plus some larger
    cands = list(range(1, 3001))
    cands += [4000, 5000, 6000, 8000, 10000, 12000, 15000, 20000]
    for T in range(0, n, 1):
        st, p1, tape1 = snaps[T]
        lst = by_state[st]
        for P in cands:
            idx = T + P
            if idx >= n:
                break
            st2, p2, tape2 = snaps[idx]
            d = p2 - p1
            if d == 0:
                continue
            if abs(d) > 50000:
                continue
            # compute [lo, hi] over lap [T, T+P]
            lo = p1
            hi = p1
            ok = True
            for i in range(T, idx + 1):
                pp = snaps[i][1]
                if pp < lo:
                    lo = pp
                if pp > hi:
                    hi = pp
                if i - T > 20000:
                    break
            # check tape2[y+d] == tape1[y] for y in [lo, hi]
            for y in range(lo, hi + 1):
                v1 = tape1.get(y, 0)
                v2 = tape2.get(y + d, 0)
                if v1 != v2:
                    ok = False
                    break
            if not ok:
                continue
            # blank outside on entering side
            if d > 0:
                for y in range(hi + 1, hi + 1 + 2000):
                    if tape2.get(y, 0) != 0:
                        ok = False
                        break
            else:
                for y in range(lo - 2000, lo):
                    if tape2.get(y, 0) != 0:
                        ok = False
                        break
            if not ok:
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