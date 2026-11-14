import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

def build_push(table, n_states, syms=(0,1), blank=0):
    # Automaton state = (depth, last n cells encoded). push_left reads cells
    # left of the head, from far away toward the head. We encode the last
    # n cells (next to head first) as a tuple, capped at n entries.
    def mk(n):
        def push(state, symbol):
            depth, cells = state
            new = (symbol,) + cells[:n-1] if n > 0 else ()
            return (min(depth+1, n), new)
        return push
    return mk

def try_cps(tm, table, n_states, target, maxcap=200000):
    # Build push functions for a window automaton of size n
    def mk_push(n):
        def push(state, symbol):
            cells = state
            new = (symbol,) + cells[:n-1] if n > 0 else ()
            return new[:n] if n > 0 else ()
        return push
    for n in range(0, 5):
        push_left = mk_push(n)
        push_right = mk_push(n)
        blank_left = ()
        blank_right = ()
        # closure() expects push functions and blanks; try to call it
        try:
            cert = closure(push_left, push_right, blank_left, blank_right, cap=maxcap)
        except TypeError:
            # try alternative signature: push_left(state, symbol) style
            cert = None
        if cert is None:
            continue
        try:
            check(tm, cert)
            return cert
        except Reject:
            continue
    return None

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # Try several window sizes of CPS via the helper
    for n in range(1, 6):
        push_left = (lambda n: (lambda state, symbol: ((symbol,) + state[:n-1])[:n]))(n)
        push_right = (lambda n: (lambda state, symbol: ((symbol,) + state[:n-1])[:n]))(n)
        try:
            cert = closure(push_left, push_right, (), (), cap=200000)
        except Exception:
            cert = None
        if cert is not None:
            try:
                check(tm, cert)
                return cert
            except Reject:
                pass
    return None
