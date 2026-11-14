from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

# --- helpers ---------------------------------------------------------------

def _state_after(tm, steps):
    """Run `steps` steps; if it halts before, return None."""
    halted, _, st, pos, tape = run(tm, steps)
    if halted:
        return None
    return st, pos, tape

def _lap(tm, T, P):
    """Simulate T steps, then P more.  Returns (st_T, tape_T, lo, hi, d, st_Tp, tape_Tp)
    or None if the machine halts."""
    a = _state_after(tm, T)
    if a is None:
        return None
    st_T, pos_T, tape_T = a
    # record positions during the lap
    lo = pos_T
    hi = pos_T
    pos = pos_T
    tape = dict(tape_T)
    st = st_T
    table, _, _ = parse(tm)
    for _ in range(P):
        key = (st, tape.get(pos, 0))
        if key not in table:
            return None
        w, mv, st2 = table[key]
        tape[pos] = w
        pos += mv
        if pos < lo:
            lo = pos
        if pos > hi:
            hi = pos
        st = st2
    return st_T, tape_T, lo, hi, pos - pos_T, st, tape

# --- decider 1: translated-window cycles ----------------------------------

# Try a range of lap lengths P and offsets T, looking for a periodic window
# whose content shifts by d each lap.  Small P first, broad T sweep.

def _try_lap(tm, T, P):
    r = _lap(tm, T, P)
    if r is None:
        return None
    st_T, tape_T, lo, hi, d, st_Tp, tape_Tp = r
    if st_T != st_Tp:
        return None
    # window content must repeat, shifted by d
    for y in range(lo, hi + 1):
        a = tape_T.get(y, 0)
        b = tape_Tp.get(y + d, 0)
        if a != b:
            return None
    # when d > 0, cells right of hi must be blank at T+P;
    # when d < 0, cells left of lo must be blank at T+P
    if d > 0:
        for y in range(hi + 1, hi + 1 + (d if d > 0 else 0)):
            pass
        # check a generous margin to the right
        for y in range(hi + 1, hi + 1 + 2000):
            if tape_Tp.get(y, 0):
                return None
    elif d < 0:
        for y in range(lo - 2000, lo):
            if tape_Tp.get(y, 0):
                return None
    cert = {"kind": "cycle", "t": T, "p": P}
    try:
        check(tm, cert)
    except Reject:
        return None
    return cert

def decide_lap(tm):
    parse(tm)
    # sweep T from 0 up to a few thousand, P from 1 up
    for P in range(1, 2001):
        for T in range(0, 4001, 1):
            if T + P > 100000:
                continue
            c = _try_lap(tm, T, P)
            if c:
                return c
    return None

# --- decider 2: last-cell-remembering CPS over a sliding window ------------

def decide(tm):
    c = decide_lap(tm)
    if c:
        return c
    return None