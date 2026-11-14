NAME = "tcycle_wide"

from neverhalt.tm import parse
from neverhalt.kernel import check, Reject


def _try(tm, t, p):
    if t + p > 100000:
        return None
    try:
        return check(tm, {"kind": "cycle", "t": t, "p": p})
    except Reject:
        return None


def decide(tm):
    try:
        tree, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    for p in (40, 48, 56, 60, 64, 72, 80, 96, 120, 128, 160, 192, 256, 320, 384, 448, 512):
        for t in range(0, 400, 1):
            cert = _try(tm, t, p)
            if cert is not None:
                return cert
    return None
