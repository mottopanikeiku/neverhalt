"""cps_small: search small half-tape automata for a closed context set.

For each remaining holdout, enumerate push automata with 1..3 states per side
(state 0 must loop on symbol 0).  For every pair (left, right) build the
smallest closed context set with the untrusted helper `closure`, and stop at
the first pair whose closure contains no halting context.  Only transitions
the closure actually used are kept in the certificate (null elsewhere).
"""

from neverhalt.tm import parse
from neverhalt.helpers import closure

# enumerate push functions for a half-tape automaton with `n` states.
# state 0 = all-blank half-tape, and push(0, 0) must be 0.
def enumerate_pushes(n):
    out = []
    for bits in range((n * 2) ** n):
        # decode bits into table[i][x] for i in range(n), x in {0,1}
        table = {}
        v = bits
        ok = True
        for i in range(n):
            for x in (0, 1):
                table[(i, x)] = v % n
                v //= n
        if table[(0, 0)] != 0:
            continue
        out.append(table)
    return out


def push_of(table, state, symbol):
    return table.get((state, symbol))


def smallest_closure(n_states, cap=200000):
    """Try every pair of n-state pushes, return first cps certificate or None."""
    pushes = enumerate_pushes(n_states)
    for lt in pushes:
        for rt in pushes:
            cert = closure(
                push_left=lambda s, x, t=lt: t[(s, x)],
                push_right=lambda s, x, t=rt: t[(s, x)],
                blank_left=0,
                blank_right=0,
                cap=cap,
            )
            if cert is not None:
                return cert
    return None


def decide(tm):
    try:
        _, n_states, _ = parse(tm)
    except Exception:
        return None
    for n in (1, 2, 3):
        cert = smallest_closure(n)
        if cert is not None:
            return cert
    return None


NAME = "cps_small"