import sys, json
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "long run detector"

def decide(tm):
    # Simulate long and look for exact state/tape periodicity (cycle certificate)
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Run long enough to catch repetitions
    try:
        halted, steps, state, pos, tape = run(tm, 100000)
    except Exception:
        return None
    if halted:
        return None
    # Attempt to find a cycle in the (state, tape) projection is hard; instead
    # try classic translated cycle: simulate and compare tape snapshots at
    # increasing lags using a rolling hash of the non-zero tape region.
    try:
        halted, steps, state, pos, tape = run(tm, 20000)
    except Exception:
        return None
    if halted:
        return None
    # Build a compact representation of the tape as a sorted list of (pos, val)
    region = dict(tape)
    # Try to find a cycle by re-simulating and comparing full configuration hashes
    # at successive times is too expensive; instead use the kernel's acceptance by
    # constructing a candidate cycle certificate from periodic patterns.
    # This decider is a placeholder that only returns None; real search happens
    # in other parallel deciders.
    return None
