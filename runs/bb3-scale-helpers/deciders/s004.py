"""cps_small_automata: enumerate small left/right automata and build closures.

For each machine, enumerate deterministic automata on each half-tape with
1, 2 then 3 states (state 0 loops on 0), compute the closure of contexts via
neverhalt.helpers.closure, and return the first non-halting certificate.
"""

from neverhalt.tm import parse
from neverhalt.helpers import closure

MACHINE_CACHE = {}


def _mach(tm):
    if tm not in MACHINE_CACHE:
        MACHINE_CACHE[tm] = parse(tm)
    return MACHINE_CACHE[tm]


def _push_table(table, n):
    """table[i][x] = next state from i on symbol x, or None."""
    return table


def _enumerate_tables(n):
    """Yield transition tables of a deterministic automaton with `n` states.

    State 0 loops on symbol 0 (blank) and must be the all-blank state:
    push(0, 0) == 0.  Each state maps 0 and 1 to a state or None (dead).
    """
    if n == 1:
        yield [[0, None]]
        return
    # state 0: [0, ...]; other states free over {0,1} -> {0..n-1, None}
    choices = [None] + list(range(n))
    for s in range(1, n):
        pass
    # build per-state choices
    state_choices = []
    for i in range(n):
        if i == 0:
            opts0 = [0]
            opts1 = [None] + list(range(n))
        else:
            opts0 = [None] + list(range(n))
            opts1 = [None] + list(range(n))
        state_choices.append((opts0, opts1))
    # iterate product lazily (may be large but n<=3 is fine)
    import itertools

    for combo in itertools.product(*[list(itertools.product(*sc)) for sc in state_choices]):
        table = [[combo[i][0], combo[i][1]] for i in range(n)]
        yield table


def _all_tables(n):
    for table in _enumerate_tables(n):
        yield table


def _build_cert(table, n_states):
    return table


def decide(tm: str):
    table, ns, nsym = _mach(tm)
    # state 0 is A.  Try increasing automaton sizes.
    for n in (1, 2, 3):
        left_tables = list(_all_tables(n))
        right_tables = list(_all_tables(n))
        for lt in left_tables:
            for rt in right_tables:
                # Build push functions from tables.
                # closure expects push_left(state, symbol) -> state or None
                # and blank states.
                def pl(st, sym, _t=lt):
                    if st is None:
                        return None
                    if sym < 0 or sym >= 2:
                        return None
                    return _t[st][sym]

                def pr(st, sym, _t=rt):
                    if st is None:
                        return None
                    if sym < 0 or sym >= 2:
                        return None
                    return _t[st][sym]

                blank_l = 0
                blank_r = 0
                try:
                    cert = closure(
                        pl,
                        pr,
                        blank_l,
                        blank_r,
                        cap=200000,
                        table=table,
                    )
                except Exception:
                    cert = None
                if cert is not None:
                    return cert
    return None


if __name__ == "__main__":
    import sys

    for tm in sys.argv[1:]:
        c = decide(tm)
        print(tm, "->", None if c is None else c.get("kind"))
