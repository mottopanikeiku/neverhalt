NAME = "window3"

from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject


def _try_cycle(tm, t, p):
    try:
        return check(tm, {"kind": "cycle", "t": t, "p": p})
    except Reject:
        return None


def decide(tm):
    try:
        tree, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # First pass: translated-cycle search with widening windows and lap budget.
    for delay in (1, 2, 2, 4, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256):
        for pmax in (delay, 2 * delay, 4 * delay, 8 * delay):
            if pmax + delay > 100000 - 5000:
                continue
            try:
                tm2, t, p = None, pmax, delay
                return _try_cycle(tm, tm2, p)
            except Exception:
                continue
    return None
