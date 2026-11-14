import itertools
from neverhalt.tm import parse
from neverhalt.helpers import closure


def _mk_push_fn(n_states, transitions):
    """Build push functions for an automaton with states 0..n_states-1.

    transitions: dict (state, symbol) -> next_state or None.
    State 0 must loop on 0 (blank half-tape).
    """
    def push(state, symbol):
        nxt = transitions.get((state, symbol))
        if nxt is None:
            return None
        return nxt
    return push


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # Machine states are ints A=0..n-1. Symbols 0,1.
    n_m = n_states
    # Enumerate small automata for each side. State 0 loops on symbol 0.
    # Automaton states 0..k-1, transitions on symbols 0 and 1.
    def enumerate_automata(k):
        # Each state has two transitions. State 0: on 0 -> 0 (forced).
        # We enumerate the rest.
        # Represent as dict (state, sym) -> next_state or None.
        free = []
        for st in range(k):
            for sym in (0, 1):
                if st == 0 and sym == 0:
                    continue
                free.append((st, sym))
        # Try all assignments: next in 0..k-1 or None
        options = [list(range(k)) + [None] for _ in free]
        for combo in itertools.product(*options):
            trans = {}
            trans[(0, 0)] = 0
            for (st, sym), val in zip(free, combo):
                trans[(st, sym)] = val
            yield trans

    # Try sizes 1, 2, 3 on each side, but that's 3^2 * (k^2+...)
    # Automaton with k states has k*2 transitions; each can be one of k+1 options.
    # k=1: 2 free transitions (state 0 on 1) -> wait, state 0 on 0 forced, state 0 on 1 free -> 2 options.
    # Actually for k states: transitions (st,sym) for st in 0..k-1, sym in 0,1, except (0,0).
    # That's 2k-1 transitions, each k+1 options.
    # k=1: 1 transition, 2 options = 2
    # k=2: 3 transitions, 3 options = 27
    # k=3: 5 transitions, 4 options = 1024
    # Pairs: (2*27 + 27*2 + 1024*1024) too many for k=3 pairs.
    # Do k=1 and k=2 pairs first, then k=3 with k<=2 on other side, then k=3/k=3 if time.

    def try_pair(left_trans, right_trans):
        # push functions
        def push_left(state, symbol):
            return left_trans.get((state, symbol))
        def push_right(state, symbol):
            return right_trans.get((state, symbol))
        blank_left = 0
        blank_right = 0
        # closure may return None or a cert
        try:
            cert = closure(push_left, push_right, blank_left, blank_right, cap=200000)
        except Exception:
            return None
        if cert is None:
            return None
        return cert

    # k=1
    for lt in enumerate_automata(1):
        for rt in enumerate_automata(1):
            c = try_pair(lt, rt)
            if c is not None:
                return c
    # k=1 on one side, k=2 on other
    for lt in enumerate_automata(1):
        for rt in enumerate_automata(2):
            c = try_pair(lt, rt)
            if c is not None:
                return c
    for lt in enumerate_automata(2):
        for rt in enumerate_automata(1):
            c = try_pair(lt, rt)
            if c is not None:
                return c
    # k=2 both
    for lt in enumerate_automata(2):
        for rt in enumerate_automata(2):
            c = try_pair(lt, rt)
            if c is not None:
                return c
    return None