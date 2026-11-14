from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# The holdouts are counters / bouncers: the head advances forever while the
# pattern left behind is a periodic "comb" of 1s and 0s.  A fixed n-gram window
# is not enough, but a tiny automaton that counts the rank of the head modulo
# a small period (or remembers a few cells) as it sweeps outward is.
#
# Plan: enumerate all deterministic automata with 1, 2 and 3 states per side
# (state 0 loops on symbol 0; transitions from any state on any symbol stay in
# the state set, and the blank all-zero half-tape is state 0).  For every pair
# (left automaton, right automaton) build the smallest closed context set with
# the provided closure helper and keep the first pair whose closure contains
# [0,0,0,0] and no halting context.  The helper already rejects halting
# closures, so we only need to test the machine's own transitions.

def _aut_states(n):
    # all functions S -> S must be total for the closure to be usable: the
    # helper only asks for transitions that are actually taken, but a total
    # table keeps the search simple and small.  We enumerate them lazily.
    funcs = []
    for t in range(n ** n):
        tab = []
        x = t
        for _ in range(n):
            tab.append(x % n)
            x //= n
        funcs.append(tab)
    return funcs

def _is_total(table):
    return len(table) == len(table[0]) if table else True

def _closure_for(tm, left_func, right_func, cap=60000):
    # Wrap the two functions as push functions on an infinite tape: the first
    # cell pushed is the one adjacent to the head; state 0 is all blank.
    n = 2
    blank_l = 0
    blank_r = 0
    def push_left(state, symbol):
        if symbol == 0:
            # blank cell: the automaton consumes it and stays/advances
            # according to the table; our tables already loop on 0 at state 0
            return left_func[state][0]
        return left_func[state][1]
    def push_right(state, symbol):
        if symbol == 0:
            return right_func[state][0]
        return right_func[state][1]
    return closure(push_left, push_right, blank_left=blank_l,
                   blank_right=blank_r, cap=cap)

def _build_tables(n):
    funcs = _aut_states(n)
    return funcs

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # quick: if it halts under 300 steps, not our machine
    try:
        h, steps, st, pos, tape = run(tm, 300)
        if h:
            return None
    except Exception:
        return None
    if n_symbols != 2:
        return None

    # enumerate automata of size 1, 2, 3 per side; try all pairs
    for n in (1, 2, 3):
        funcs = _build_tables(n)
        for lf in funcs:
            for rf in funcs:
                # quick sanity: state 0 must loop on symbol 0
                if lf[0][0] != 0 or rf[0][0] != 0:
                    continue
                try:
                    cert = _closure_for(tm, lf, rf)
                except Exception:
                    cert = None
                if cert is None:
                    continue
                try:
                    kind = check(tm, cert)
                    if kind:
                        return cert
                except Reject:
                    continue
                except Exception:
                    continue
    return None
