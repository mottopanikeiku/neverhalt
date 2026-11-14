import sys
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

# We enumerate pairs of automata (one per half-tape) with 1..3 states each.
# State 0 is the all-blank half-tape: it must loop on symbol 0.
# For every other state and every symbol (0 or 1) we may choose:
#   - a next state, or
#   - None meaning "this symbol never occurs in a valid half-tape".
# We build the push functions, run closure, and if it returns a certificate
# we hand it over.  The closure helper keeps only the transitions that were
# actually used, which is exactly what the kernel requires.

SYMS = (0, 1)


def make_automaton(nstates, spec):
    # spec: dict mapping (state, symbol) -> next state or None
    blank = 0

    def push(state, symbol):
        nxt = spec.get((state, symbol))
        return nxt

    return push, blank


def all_specs(nstates):
    keys = [(s, x) for s in range(nstates) for x in SYMS]
    # state 0 loops on symbol 0
    choices = []
    for k in keys:
        if k == (0, 0):
            choices.append([(0,)])
        else:
            choices.append([(None,)] + list(range(nstates)))
    import itertools

    for combo in itertools.product(*choices):
        spec = dict(zip(keys, combo))
        spec[(0, 0)] = 0
        yield spec


def build_decider():
    # cache certificates per tm is done by the caller; here we build tables once.
    for n in (1, 2, 3):
        for spec in all_specs(n):
            yield spec


def decide(tm):
    # quick pre-check that the closure helper can handle this tm
    try:
        table, nstates, nsym = parse(tm)
    except Exception:
        return None

    # machine state -> int, symbol -> 0/1.  Build push functions for each side.
    # The push function receives the automaton state and the symbol being pushed
    # and returns the new automaton state.
    mstates = list(range(nstates))

    tried = 0
    for n in (1, 2, 3):
        for spec in all_specs(n):
            tried += 1
            if tried > 400:
                # budget guard
                return None
            # left automaton reads cells left of the head towards the head;
            # right automaton reads cells right of the head towards the head.
            # We try both orientations for the same spec (they are independent
            # halves and the closure helper takes one push function per side).
            pl, bl = make_automaton(n, spec)
            try:
                cert = closure(pl, pl, table)
            except Exception:
                continue
            if cert is None:
                continue
            try:
                kind = check(tm, cert)
            except Reject:
                continue
            if kind:
                return cert
    return None
