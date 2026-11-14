import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

sys.setrecursionlimit(10000)

from neverhalt.helpers import closure


def _ngram_state(n):
    # state = tuple of last n symbols (0 = blank), leftmost slot first
    return lambda: None


def _push_factory(n, side):
    """Automaton remembering the last n cells read, n-gram style."""
    blank = (0,) * n

    def push(st, sym):
        if st is None:
            st = blank
        return (st[1:], sym)

    return push, blank


def _enumerate_tables(max_states):
    """Enumerate deterministic automata with up to max_states states,
    state 0 loops on symbol 0. Return list of (states, table, blank)."""
    out = []
    for n in range(1, max_states + 1):
        # table[s] must be a function from state to state or None
        # represent as list of length n, each entry either None or state index
        # enumerate all functions {0,1} -> {None} U [0,n)
        import itertools
        choices = [None] + list(range(n))
        for combo in itertools.product(choices, repeat=n * 2):
            tab = {}
            ok = True
            for st in range(n):
                for sym in (0, 1):
                    idx = st * 2 + sym
                    v = combo[idx]
                    if v is None:
                        tab[(st, sym)] = None
                    else:
                        tab[(st, sym)] = v
            # state 0 loops on symbol 0
            if tab[(0, 0)] != 0:
                continue
            out.append((n, tab, 0))
    return out


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # machine state -> index 0..n_states-1
    # We use the closure helper with push functions (n-gram automata).
    # Try increasing n-gram sizes and pick first that yields certificate.
    for n in range(1, 5):
        push_l, blank_l = _push_factory(n, 'L')
        push_r, blank_r = _push_factory(n, 'R')
        try:
            cert = closure(push_left=push_l, push_right=push_r,
                           blank_left=blank_l, blank_right=blank_r,
                           cap=200000)
        except Exception:
            cert = None
        if cert is not None:
            try:
                check(tm, cert)
            except Reject:
                continue
            return cert
    return None
