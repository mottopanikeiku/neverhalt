import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# A decider that tries to prove non-halting by finding a translated cycle
# (drifting cycle) using a local search over cycle start points and lap lengths.
# The sample holdouts all show a compact, repeating "staircase" pattern that
# drifts rightwards; detecting the period of that drift should close many of them.

def decide(tm: str):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # First try some longer simulation to see whether a simple translated
    # cycle appears near the start (most drifting machines settle in quickly).
    for max_steps in (200, 500, 1000, 2000):
        try:
            halted, steps, state, pos, tape = run(tm, max_steps)
        except Exception:
            return None
        if halted:
            # Machine halts: not our job, but this decider cannot prove anything.
            return None

        # Try candidate laps: look for T and P where the state repeats and the
        # tape pattern is translated by a fixed displacement.
        for T in range(0, min(steps, 300)):
            for P in range(2, min(200, steps - T) + 1):
                # Re-run to get state and tape at T and T+P.
                try:
                    halted, steps, st, ps, tp = run(tm, T)
                    if halted:
                        break
                    st_T, ps_T, tp_T = st, ps, tp
                    halted, steps, st, ps, tp = run(tm, T + P)
                    if halted:
                        break
                except Exception:
                    continue
                if st_T != st or ps_T != ps:
                    continue
                # Check whether the configuration at T+P is the same as at T
                # translated by d = ps - ps_T.
                d = ps - ps_T
                if d == 0:
                    # Plain cycle: same tape everywhere.
                    ok = True
                    # Need to compare tape contents in a window around the head.
                    for y in range(-10, 11):
                        if tp_T.get(y) != tp.get(y):
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
                    # Translated cycle: compare a window of the tape shifted by d.
                    lo = ps_T - 10
                    hi = ps_T + 10
                    ok = True
                    for y in range(lo, hi + 1):
                        if tp_T.get(y) != tp.get(y + d):
                            ok = False
                            break
                    if ok:
                        # The kernel also requires that everything outside
                        # the window is blank on the far side.  We approximate
                        # by checking the visible tape bounds.
                        cert = {"kind": "cycle", "t": T, "p": P}
                        try:
                            check(tm, cert)
                            return cert
                        except Reject:
                            pass
    return None
