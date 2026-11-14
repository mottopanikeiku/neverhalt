import itertools
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject

try:
    from neverhalt.helpers import closure
except Exception:
    closure = None


def _build_automaton(nstates):
    """Enumerate all transition tables for a small automaton.

    State 0 loops on symbol 0 (blank).  On symbol 1 state 0 may go to
    any other state.  Every other state has an arbitrary destination on
    both symbols (or loops).
    """
    tables = []
    # left[i][x]
    for i in range(nstates):
        for x in (0, 1):
            if i == 0 and x == 0:
                continue
            choices = list(range(nstates))
            if i == 0 and x == 1:
                choices = list(range(nstates))
            tables.append((i, x, choices))
    # cartesian product
    def rec(idx, cur):
        if idx == len(tables):
            yield cur
            return
        i, x, choices = tables[idx]
        for c in choices:
            nxt = dict(cur)
            nxt[(i, x)] = c
            yield from rec(idx + 1, nxt)
    return rec(0, {})


def _to_push(table, nstates):
    def push(state, symbol):
        return table.get((state, symbol), state)
    return push, state0


def decide(tm):
    try:
        t, ns, nsm = parse(tm)
    except Exception:
        return None
    # ensure blank state convention: state 0 loops on 0
    # try pairs of small automata
    for n1 in (1, 2, 3):
        for n2 in (1, 2, 3):
            for ta in _build_automaton(n1):
                for tb in _build_automaton(n2):
                    pl = ta.get((0, 0), 0)
                    pr = tb.get((0, 0), 0)
                    # build pushes with explicit blank loop
                    def mk(t, blank):
                        def push(state, symbol):
                            if symbol == 0:
                                return t.get((state, 0), blank)
                            return t.get((state, 1), blank)
                        return push
                    try:
                        cert = closure(mk(ta, 0), mk(tb, 0), 0, 0, 200000)
                    except Exception:
                        cert = None
                    if cert is None:
                        continue
                    try:
                        check(tm, cert)
                    except Reject:
                        continue
                    return cert
    return None
