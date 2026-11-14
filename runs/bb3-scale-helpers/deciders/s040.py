import itertools
from neverhalt.tm import parse
from neverhalt.helpers import closure

def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # normalize machine states to 0..n_states-1
    for q in range(n_states):
        s = table[q][0]  # not used; table indexing by state int
    # build push functions for half-tapes of bounded window length n
    # push_left(state, symbol): state is the memory of the last n cells
    # read order: far away towards the head.  We keep the window as a
    # tuple of cells, oldest (far) first.  A new cell enters at the far
    # side when the head moves right (it writes the cell it leaves
    # behind).  So push_left(state, x) = (x,) + state[1:] conceptually
    # but we must drop the oldest only when window is full.
    # We will define push functions for a fixed n, and try n = 0,1,2,3.
    for n in range(0, 4):
        if _try_n(tm, n):
            return None  # nothing found; caller treats as no certificate
    return None

def _try_n(tm, n):
    table, n_states, n_symbols = parse(tm)
    # state 0 of the machine is A
    # automaton state = tuple of length n of cells (0/1), stored oldest->newest
    # state 0 is the all-blank half-tape = (0,)*n
    blank = (0,) * n

    def push_left(state, symbol):
        # head moves right: the cell just written becomes the far cell of the
        # left half-tape (we read left cells from far to near).  New symbol
        # is at the far side, so prepend; if full, drop the oldest (which is
        # the one furthest away, i.e., the leftmost of the tuple).  Wait:
        # reading left of head from far away towards the head means the
        # first symbol read is the furthest cell.  When head moves right,
        # the cell immediately left of the head becomes the nearest cell,
        # and the previously nearest cell is now farther.  So the reading
        # order tuple = (far, ..., near).  The new near cell is the written
        # symbol.  So append to the right and drop the leftmost if full.
        t = state + (symbol,)
        if len(t) > n:
            t = t[1:]
        return t

    def push_right(state, symbol):
        # mirror: reading right cells from far to near; new near cell is
        # written symbol; append and drop leftmost if full.
        t = state + (symbol,)
        if len(t) > n:
            t = t[1:]
        return t

    cert = closure(table, n_states, push_left, push_right, blank, blank, cap=200000)
    if cert is not None:
        return True
    return False

# Actually return the certificate when found.
def decide(tm):
    table, n_states, n_symbols = parse(tm)
    for n in range(0, 4):
        cert = closure(table, n_states, _mk(n)[0], _mk(n)[1], _mk(n)[2], _mk(n)[2], cap=200000)
        if cert is not None:
            return cert
    return None

def _mk(n):
    blank = (0,) * n
    def push_left(state, symbol):
        t = state + (symbol,)
        if len(t) > n:
            t = t[1:]
        return t
    push_right = push_left
    return push_left, push_right, blank
