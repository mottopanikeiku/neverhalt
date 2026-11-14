import itertools
from neverhalt.tm import parse, run
from neverhalt.helpers import closure

# Build push functions for a given transition table of size n.
# table[(state, symbol)] -> next_state or None (dead).
def make_pushes(table, n):
    def push(state, symbol):
        if state is None:
            return None
        return table.get((state, symbol), None)
    return push

def try_table(n, cap):
    # enumerate all transition tables with n states, symbols {0,1}
    # state 0 must loop on 0: table[(0,0)] = 0
    choices = []
    for s in range(n):
        for sym in (0, 1):
            if s == 0 and sym == 0:
                continue
            choices.append((s, sym))
    # each choice: next state in 0..n-1, or None (dead)
    for combo in itertools.product(range(n), repeat=len(choices)):
        table = {(0, 0): 0}
        for (s, sym), nx in zip(choices, combo):
            table[(s, sym)] = nx
        # blank state 0 must loop on 0, which it does.
        pl = make_pushes(table, n)
        pr = make_pushes(table, n)
        cert = closure(pl, pr, cap)
        if cert is not None:
            # verify the certificate has no halting context (closure already ensures)
            return cert
    return None

def decide(tm):
    try:
        table, n_states, n_symbols = parse(tm)
    except Exception:
        return None
    # build the machine transition table in terms of (state, symbol) -> (write, move, next)
    # For CPS we need pushes that model the machine's writes.
    # The standard construction: the push function reads the symbol that was written
    # when the head moved away from this half, and the state before that move.
    # We build automata over the machine's own states as a first attempt (n-gram style),
    # but the hint asks for small independent automata. We try small automata
    # whose states are machine states plus a small counter, starting with plain
    # n-gram style: state = (last k cells). Instead, follow the hint literally:
    # enumerate small automata and use closure.
    # The closure helper expects push_left(push state, symbol) -> new state,
    # where a push happens when the head moves away from that half-tape,
    # reading the symbol that was just written.
    # We first try the trivial n-gram-style push: state = tuple of last k symbols.
    # But the hint says enumerate small automata. Let's do that.
    # For k in 1..3, try all automata of size up to 3 states per side,
    # with state 0 looping on 0.
    cap = 200000
    for n in (1, 2, 3):
        cert = try_table(n, cap)
        if cert is not None:
            return cert
    return None
