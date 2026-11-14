from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _build_automata(ns):
    """All deterministic automata with ns states, state 0 looping on 0.
    States are ints; state i maps symbol x to j or None (never happens)."""
    out = []
    if ns == 1:
        yield [0]
        return
    # state 0: on symbol 0 -> 0 always. On symbol 1 -> some state in [0,ns)
    # other states: on 0/1 -> some state in [0,ns) or None
    states = list(range(ns))
    # symbol 0 from state 0 is fixed to 0
    choices_0_0 = [0]
    choices_0_1 = states
    choices_other = [None] + states
    for c01 in choices_0_1:
        for others in _product_others(ns, choices_other):
            table = [None, None]
            table[0] = [0, c01]
            for i in range(1, ns):
                table[i] = [others[2 * (i - 1)], others[2 * (i - 1) + 1]]
            out.append(table)
    return out


def _product_others(ns, choices):
    if ns == 1:
        yield ()
        return
    for a in choices:
        for b in choices:
            rest = yield from _product_others(ns - 1, choices)
            for r in rest:
                yield (a, b) + r


def _make_push(table):
    def push(state, symbol):
        t = table[state]
        if t is None:
            return None
        nxt = t[symbol]
        if nxt is None:
            return None
        return nxt
    return push


def _blank_push(table, blank):
    def push(state, symbol):
        t = table[state]
        if t is None:
            return None
        nxt = t[symbol]
        if nxt is None:
            return None
        return nxt
    return push


def _make_cps(tm):
    table, n_states, n_symbols = parse(tm)
    # build pair of automata tables (list of ns states each)
    # for ns in 1..3
    # use closure helper with push functions
    # push_left(state, symbol) returns new state after reading symbol next to head on left
    # We construct automata with state 0 = blank half-tape (loops on 0).
    results = []
    for ns in (1, 2, 3):
        autos = _build_automata(ns)
        if ns == 1:
            autos = [[0]]
        for A in autos:
            for B in autos:
                # normalize so blank states are the same index 0 for both (they are)
                # push functions
                pushL = _make_push(A)
                pushR = _make_push(B)
                try:
                    cert = closure(pushL, pushR)
                except Exception:
                    cert = None
                if cert is not None:
                    # cert is already a cps dict; verify
                    try:
                        check(tm, cert)
                        return cert
                    except Reject:
                        continue
    return None


def decide(tm: str) -> dict | None:
    try:
        return _make_cps(tm)
    except Exception:
        return None
