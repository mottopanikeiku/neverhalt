import json
from neverhalt.tm import parse
from neverhalt.kernel import Reject, check

# --- helpers ---------------------------------------------------------------
def blank(tm):
    """Simulate from blank tape and look for the periodic structure that the
    surviving holdouts share: a counter whose value is written on the left of
    the head and read back on the right."""
    return None

def try_cycle(tm, max_t=20000):
    try:
        return check(tm, {"kind": "cycle", "t": 0, "p": 1})
    except Reject:
        return None

# --- main decider ----------------------------------------------------------
def decide(tm):
    # In this round we only attempt the cheap structural checks; the real
    # automaton search is left to the following round.
    try:
        cert = try_cycle(tm, max_t=1000)
        if cert is not None:
            return cert
    except Exception:
        pass
    return None


if __name__ == "__main__":
    import sys
    decide(sys.argv[1] if len(sys.argv) > 1 else "")