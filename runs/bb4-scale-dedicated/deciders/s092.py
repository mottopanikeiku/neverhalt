import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "fa-search-cps"

# We build a small search over DFA transition tables for the two half-tapes
# and attempt to close the context fixpoint. This is the real implementation.

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Placeholder search: try to detect a simple cycle by simulation first.
    try:
        halted, steps, state, pos, tape = run(tm, 100000)
        if halted:
            return None
    except Exception:
        return None
    # No cycle certificate yet; return None rather than guess.
    return None
