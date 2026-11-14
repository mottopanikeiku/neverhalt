NAME = "tcycle4"

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _try(tm, t, p):
    try:
        return check(tm, {"kind": "cycle", "t": t, "p": p})
    except Reject:
        return None


def decide(tm):
    try:
        tree, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Lap lengths one plausibly completes a period-2/4 window step.
    for p in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96):
        for t in range(0, 400):
            if t + p > 100000:
                break
            cert = _try(tm, t, p)
            if cert is not None:
                return cert
    return None
