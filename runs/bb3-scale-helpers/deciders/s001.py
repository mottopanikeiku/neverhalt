import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# Small decider: try a library of hand-built (push_left, push_right) automaton pairs
# designed for counters/bouncers, using the sandboxed closure helper.

def _mk_automaton(remember):
    # remember: set of symbols the automaton tracks (e.g. {0,1})
    # state is a tuple of recent symbols (n-gram), but we let closure pick.
    return None

def _ngram_push(n, blank):
    def push(state, sym):
        # state: tuple of last n symbols, blank is ()
        if state is None:
            state = blank
        return (state + (sym,))[-n:]
    return push

def _counter_push(blank):
    # state: (count, parity) or None for 0; count how many non-blank seen
    def push(state, sym):
        if sym == 0:
            return blank
        if state is None:
            return (1, 0)
        return (state[0] + 1, (state[1] + sym) % 2)
    return push

def _bounce_push(blank):
    # state: (last symbol, direction), direction encodes how many steps since a change
    def push(state, sym):
        if sym == 0:
            return blank
        if state is None:
            return (sym, 1)
        return (sym, state[1] + 1)
    return push

def _try_pushes(tm, pairs):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    automata_pairs = []
    for n in (1, 2, 3):
        automata_pairs.append((_ngram_push(n, ()), _ngram_push(n, ())))
    automata_pairs.append((_counter_push(None), _counter_push(None)))
    automata_pairs.append((_bounce_push(None), _bounce_push(None)))
    for pl, pr in automata_pairs:
        try:
            cert = closure(pl, pr)
        except Exception:
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
    return _try_pushes(tm, None)

