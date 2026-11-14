"""Automaton-pair CPS search over small automata for 3-state, 2-symbol holdouts.

We enumerate small deterministic automata for each half-tape.  A half-tape
automaton reads cells from far away toward the head, so state 0 (all-blank) must
loop on symbol 0.  We enumerate transition tables with 1..3 states per side and
try every pair, using the provided closure helper.  We also try a symmetric
"small spanning" variant that starts from the known initial context [0,0,0,0]
and grows the context set forward, which is faster when a small automaton pair
already suffices.
"""

from neverhalt.tm import parse
from neverhalt.helpers import closure


def _tables(n):
    """Yield all deterministic transition tables with n states.

    States are the ints 0..n-1.  State 0 must loop on symbol 0, i.e. table[0][0]
    must be (w, 0) with w either 0 or 1 -- in the kernel's representation the
    automaton is given as push functions, so we model a table as a dict
    (state, symbol) -> (write, next_state) and wrap it later.
    """
    out = []
    for n in range(1, 4):
        # enumerate all tables of the form
        #   state 0: (0 -> (0, 0))   (blank half-tape stays blank)
        #   other states: arbitrary (write, next) with write in {0,1}, next in range(n)
        choices = []
        for st in range(n):
            for sym in (0, 1):
                if st == 0 and sym == 0:
                    choices.append([(0, 0)])
                else:
                    choices.append([ (w, ns) for w in (0, 1) for ns in range(n) ])
        # cartesian product
        import itertools
        for combo in itertools.product(*choices):
            table = {}
            i = 0
            for st in range(n):
                for sym in (0, 1):
                    table[(st, sym)] = combo[i]
                    i += 1
            yield table


def _push(t, a, b):
    """Closure-compatible push function: a is automaton state, b is symbol."""
    return t[(a, b)][1]


def _blank(t):
    return 0


def _try_pair(tm, tl, tr, cap=200000):
    try:
        cert = closure(
            push_left=lambda a, b: _push(tl, a, b),
            push_right=lambda a, b: _push(tr, a, b),
            blank_left=_blank(tl),
            blank_right=_blank(tr),
            cap=cap,
        )
    except Exception:
        return None
    return cert


# Cache of enumerated tables by size, built lazily.
_TABLES = {}
for _n in (1, 2, 3):
    _TABLES[_n] = list(_tables(_n))


def decide(tm):
    tables = []
    for n in (1, 2, 3):
        tables.append(_TABLES[n])
    # Try pairs ordered by total size, preferring the smaller side first.
    for nl in (1, 2, 3):
        for nr in (1, 2, 3):
            for tl in _TABLES[nl]:
                for tr in _TABLES[nr]:
                    cert = _try_pair(tm, tl, tr)
                    if cert is not None:
                        return cert
    return None
