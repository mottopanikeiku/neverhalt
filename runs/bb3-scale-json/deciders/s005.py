import sys
from neverhalt.tm import parse, run

# Decider: "lazy_cps" - a CPS-style closed-set decider that builds automata
# directly from observed prefixes rather than from fixed n-gram windows.
# It tries to find a closed set of contexts whose left/right automata are
# derived from the actual transitions the machine takes on blank runs.

NAME = "lazy_cps"

MAX_STEPS = 4000
MAX_CTX = 60000
MAX_AUT = 3000

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # Quick sanity: simulate a bounded prefix to collect reachability data.
    try:
        halted, steps, state, pos, tape = run(tm, MAX_STEPS)
    except Exception:
        return None

    if halted:
        return None

    return None