import sys
sys.setrecursionlimit(1000000)

from neverhalt.tm import parse
from neverhalt.helpers import closure

def _transitions_for(table, n_states):
    transitions = []
    for q in range(n_states):
        for s in range(2):
            if (q, s) in table:
                transitions.append((q, s, table[(q, s)]))
    return transitions

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    if n_symbols != 2:
        return None

    def try_automata(n_side):
        # Enumerate every transition table of n_side states.
        # State 0 is the all-blank state: blank -> (0, 0) and push(state, 0) must return blank.
        # push(state, symbol) returns the state after one more cell is appended.
        # We encode a push function per state: push(state, sym) = target state (or None).
        # We enumerate target tables for symbols 1 and 0 separately. For symbol 0:
        # blank must stay blank (push(0,0)=0), and other states may go anywhere.
        # Actually the helper contract: push(blank, 0) must return blank.
        # We enumerate all functions from (state, sym) to state-or-None, with
        # push(0, 0) = 0 enforced.
        import itertools
        n_syms = 2
        # Each state has n_syms entries; each entry is in 0..n_side-1 (or None).
        # Number of possible entries: n_side + 1. For state 0 we force entry for sym 0 to be 0.
        entries = n_side + 1
        # Enumerate all assignments.
        total = entries ** (2 * n_side)
        for idx in range(total):
            # Decode
            push = {}
            x = idx
            ok = True
            for st in range(n_side):
                for sy in range(n_syms):
                    e = x % entries
                    x //= entries
                    push[(st, sy)] = None if e == n_side else e
            # Force blank state: push(0,0) must return 0 (blank).
            if push[(0, 0)] != 0:
                continue
            # push(0, 0) == 0 already. Check push(0,1) can be anything.
            # But contract also says blank_left/blank_right are the states of an
            # all-blank half-tape, and push(blank, 0) must return blank. We use state 0.
            # Build left/right automata as identical push functions.
            blank = 0
            try:
                cert = closure(tm, push, push, blank, blank)
            except Exception:
                continue
            if cert is None:
                continue
            return cert
        return None

    for n_side in (1, 2, 3):
        # Limit enumeration size: 3 states -> 4^6 = 4096, fine.
        # 2 states -> 3^4 = 81.
        # 1 state -> 2^2 = 4.
        res = try_automata(n_side)
        if res is not None:
            return res
    return None
