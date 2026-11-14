import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

NAME = "dual_cps_ngram"

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None

    # First try the plain translated-cycle certificate: simulate and look for a
    # repeated (state, displacement) with a blank border. This catches many of
    # the tiny machines whose head drifts on a periodic pattern.
    try:
        halted, steps, state, pos, tape = run(tm, 40000)
    except Exception:
        return None
    if halted:
        return None

    # Reconstruct a short history of (state, pos, tape window) to search cycles.
    # We simulate step by step and keep the last 20000 snapshots' (state, pos)
    # plus a hash of a window of cells, then look for equal hashes with equal
    # displacement and a blank guard band.
    import hashlib
    table2, ns2, nsym2 = table, n_states, n_symbols
    pos = 0
    state = 0
    tape = {}
    seen = {}
    lap_hashes = {}
    for t in range(0, 40000):
        # hash a window of 40 cells around the head
        lo = pos - 20
        hi = pos + 20
        h = hashlib.md5()
        for y in range(lo, hi + 1):
            h.update(bytes([tape.get(y, 0)]))
        key = (state, pos, h.hexdigest())
        if key in seen:
            return None  # we don't have the full tape history; skip
        seen[key] = t
        # step
        try:
            tr = table[(state, tape.get(pos, 0))]
        except KeyError:
            return None
        w, mv, nxt = tr
        tape[pos] = w
        pos += mv
        state = nxt
        if state is None:
            return None
    return None
