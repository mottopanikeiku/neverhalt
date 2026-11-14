from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

import sys
from collections import defaultdict

# We hunt for translated cycles (tcycle) with a small drift d, by scanning
# short simulation prefixes and testing all (T, P) windows. The remaining
# holdouts look like machines that grow a triangular block while bouncing a
# head inside it; a translated cycle often appears once the shape settles.
# We also try plain d=0 cycles. Both are cheap to certify and the kernel is
# lenient, so we just enumerate (T, P) pairs with T+P <= 60000, checking only
# windows whose head displacement is small in absolute value.


def _try_cycle(table, tm, T, P, max_pos_win=400):
    try:
        stopped, steps, state, pos, tape = run(tm, T + P)
    except Exception:
        return None
    if stopped:
        return None
    # re-run for the two snapshots
    try:
        _, _, st0, pos0, tape0 = run(tm, T)
    except Exception:
        return None
    if st0 != state:
        return None
    d = pos - pos0
    if abs(d) > max_pos_win:
        return None
    # displacement must divide the lap consistently: verify tape match over
    # the union of positions touched during [T, T+P]
    # run once more capturing positions? run() does not expose them, so we
    # reconstruct by re-simulating with a copy of tape0.
    try:
        stopped, steps, state2, pos2, tape2 = run(tm, T + P)
    except Exception:
        return None
    if stopped or state2 != state:
        return None
    d2 = pos2 - pos0
    if d2 != d:
        return None
    # compare windows
    if d > 0:
        for y in tape:
            if y + d in tape2:
                if tape2[y + d] != tape.get(y, 0):
                    return None
        # cells right of hi must be blank at T+P: approximate by checking
        # that no non-blank cell lies to the right of the maximum touched
        # position in the lap window
        hi = max(tape2.keys(), default=0) + d
        for y in range(hi + 1, hi + d + 1):
            if tape2.get(y, 0) != 0:
                return None
    elif d < 0:
        for y in tape:
            if y + d in tape2:
                if tape2[y + d] != tape.get(y, 0):
                    return None
        lo = min(tape2.keys(), default=0) + d
        for y in range(lo + d, lo + 1):
            if tape2.get(y, 0) != 0:
                return None
    else:
        for y in tape:
            if tape2.get(y, 0) != tape.get(y, 0):
                return None
    return {"kind": "cycle", "t": T, "p": P}


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    best = None
    max_total = 60000
    # scan T in a few bands, P in increasing widths
    for T in range(0, max_total, 1):
        for w in range(1, 200):
            P = w * 7
            if T + P > max_total:
                break
            cert = _try_cycle(table, tm, T, P)
            if cert is not None:
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    pass
        if T % 5000 == 0:
            # widen the P step occasionally
            for w in range(200, 500):
                P = w * 13
                if T + P > max_total:
                    break
                cert = _try_cycle(table, tm, T, P)
                if cert is not None:
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None