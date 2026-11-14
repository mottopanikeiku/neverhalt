from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

import itertools


def _build_automata_pairs(max_states):
    """Yield (left_table, right_table) pairs of small deterministic automata.

    State 0 is reserved for the all-blank half-tape and must loop on symbol 0.
    We enumerate all transition tables over {0,1} for states 1..n-1 and force
    state 0 to be a self-loop on 0; on symbol 1 state 0 either goes to state 0
    or to any state (so the blank half-tape can 'notice' a nonblank cell).
    """
    for n_states in range(1, max_states + 1):
        others = list(range(1, n_states))
        for left_choices in itertools.product(range(n_states), repeat=2 * n_states):
            # left_choices encodes, for each state 0..n_states-1, its targets on 0 and 1.
            # state 0 target on 0 is forced to 0.
            left_tab = []
            for st in range(n_states):
                t0 = left_choices[2 * st]
                t1 = left_choices[2 * st + 1]
                if st == 0 and t0 != 0:
                    break
                left_tab.append([t0, t1])
            else:
                yield left_tab


def _closure_for(tm, left_tab, right_tab):
    """Try to build a cps certificate with the given automata tables."""
    # push functions: automaton state -> (new state, symbol) is represented by
    # a transition table indexed by symbol.
    blank_left = 0
    blank_right = 0

    def push_left(state, symbol):
        if symbol not in (0, 1):
            return None
        return left_tab[state][symbol]

    def push_right(state, symbol):
        if symbol not in (0, 1):
            return None
        return right_tab[state][symbol]

    return closure(push_left, push_right, blank_left, blank_right, cap=200000)


def _make_decider():
    """Return a decide(tm) function implementing the search."""

    def decide(tm):
        try:
            table, n_states, n_symbols = parse(tm)
        except Exception:
            return None
        if n_symbols != 2:
            return None

        # Quick halting check: if it halts within a bounded horizon, no certificate.
        try:
            halted, steps, state, pos, tape = run(tm, 2000)
        except Exception:
            return None
        if halted:
            return None

        # Search over small automata pairs, smallest first.
        for left_tab in _build_automata_pairs(3):
            for right_tab in _build_automata_pairs(3):
                cert = _closure_for(tm, left_tab, right_tab)
                if cert is not None:
                    try:
                        check(tm, cert)
                    except Reject:
                        continue
                    return cert
        return None

    return decide


def decide(tm: str):
    return _make_decider()(tm)