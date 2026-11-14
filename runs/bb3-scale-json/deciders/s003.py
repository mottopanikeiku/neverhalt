import sys
sys.setrecursionlimit(1000000)

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# Decider: "laterm_aware"
# Strategy: search for translated cycles (tcycle) with larger t/p budgets, and
# also try to detect machines that are "building a wall" and then bouncing,
# i.e. try to find a state at time T whose (state,pos) pair recurs with a tape
# displacement, allowing the window to be big. We search T up to a budget,
# track states and positions, and for each candidate T try laps P up to a
# budget. This is basically the kernel's cycle search but we do it ourselves
# with a bigger search and also try to detect leftward drift (d < 0) which
# the kernel accepts too. We don't need to worry about correctness: any
# certificate we return is checked by the kernel, so we can return anything
# that check() accepts. We also return None for machines where we can't find
# a certificate.

# We use the kernel's check() to validate before returning, so our decider
# is safe: it never returns a bad certificate.

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Simulate and record (state, pos) history, tape snapshots.
    try:
        # Run for a while, recording history.
        max_steps = 30000
        # We'll manually simulate to record history.
        tape = {}
        state = 0
        pos = 0
        hist = []  # (state, pos, tape_copy?)
        # tape_copy is expensive; record only positions/content near head.
        # Simpler: record full tape at each step as a dict copy, but that's
        # heavy. Instead record (state, pos) and tape as dict at each step
        # for steps up to max_steps only if n_states small.
        # We'll just record (state, pos) and the tape dict (shallow copy).
        steps_done = 0
        states_hist = []
        pos_hist = []
        tape_hist = []
        while steps_done < max_steps:
            # record
            snap = dict(tape)
            states_hist.append(state)
            pos_hist.append(pos)
            tape_hist.append(snap)
            if (state, pos) not in table:
                break
            w, mv, ns = table[(state, tape.get(pos, 0))]
            tape[pos] = w % 2
            pos += mv
            state = ns
            steps_done += 1
        # Search for translated cycles: for T in range, for P in range,
        # check state equal and tape shift.
        # We'll cap T and P.
        T_max = min(max_steps - 1, 3000)
        P_max = 3000
        # Precompute displacement and window for each (T,P) lazily.
        # Naive O(T_max*P_max) too big; instead for each T, for each P check
        # state equality first.
        # Also try to detect "wall bouncing": if the head never goes beyond
        # some position for a long time and oscillates, maybe a plain cycle
        # with d != 0 will be found.
        n = len(states_hist)
        for T in range(0, min(n - 1, T_max)):
            st = states_hist[T]
            posT = pos_hist[T]
            tapeT = tape_hist[T]
            # try P
            for P in range(1, min(n - T, P_max)):
                if states_hist[T + P] != st:
                    continue
                posP = pos_hist[T + P]
                d = posP - posT
                # compute window [lo, hi] of head positions during lap
                lo = posT
                hi = posT
                for k in range(T, T + P):
                    if pos_hist[k] < lo: lo = pos_hist[k]
                    if pos_hist[k] > hi: hi = pos_hist[k]
                # check tape shift: tape_{T+P}[y+d] == tape_T[y] for y in [lo,hi]
                tapeP = tape_hist[T + P]
                ok = True
                for y in range(lo, hi + 1):
                    # tape value at position y at time T
                    vT = tapeT.get(y, 0)
                    vP = tapeP.get(y + d, 0)
                    if vT != vP:
                        ok = False
                        break
                if not ok:
                    continue
                # blank outside window condition
                if d > 0:
                    # every cell right of hi is blank at T+P
                    for y in range(hi + 1, hi + 1 + abs(d) + 5):
                        if tapeP.get(y, 0) != 0:
                            ok = False
                            break
                    if not ok:
                        continue
                elif d < 0:
                    for y in range(lo - 1 - abs(d) - 5, lo):
                        if tapeP.get(y, 0) != 0:
                            ok = False
                            break
                    if not ok:
                        continue
                # build cert
                cert = {"kind": "cycle", "t": T, "p": P}
                try:
                    from neverhalt.kernel import check
                    check(tm, cert)
                    return cert
                except Exception:
                    continue
        # Fallback: try CPS with n-gram automata up to length 2 or 3
        # (already covered by earlier decider, but maybe try a different
        # window size here).
        # We'll just return None; earlier deciders cover CPS.
        return None
} for your review. I tried a direct translated-cycle search with a larger step budget and both leftward and rightward drift, validating every certificate through the trusted kernel before returning it. If a lap repeats with the right tape shift, this returns a verifiable certificate; otherwise it falls back to None and leaves the remaining holdouts for the next round.