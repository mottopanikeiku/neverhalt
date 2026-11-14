from neverhalt.tm import parse
from neverhalt.kernel import Reject
from neverhalt.helpers import closure

# Skip machines with no holdout behaviour (none expected).
# We enumerate small half-tape automata and use closure() to build a cps certificate.


def _push_tables(n, cap):
    """Yield push functions (blank_left, blank_right) for all automata with
    n states (0..n-1) where state 0 loops on symbol 0 and is the blank state."""
    # Each automaton is a function (state, symbol) -> next state, or None.
    # We enumerate all transition tables for states 1..n-1 on symbols {0,1}.
    # blank state 0: push(0,0) must return 0. For simplicity we only allow
    # push(0,0)=0 and push(0,1)=0 as well (blank half-tape never changes).
    from itertools import product
    cells = [(s, x) for s in range(n) for x in (0, 1)]
    # Enumerate all assignments for states 1..n-1 (state 0 fixed to 0).
    free = [(s, x) for s in range(1, n) for x in (0, 1)]
    total = len(free)
    for bits in product(range(n), repeat=total):
        table = {0: 0}
        for (s, x), b in zip(free, bits):
            table[(s, x)] = b
        yield table


def _make_push(table, blank):
    def push(state, symbol):
        if symbol == 0 and state == blank:
            return blank
        return table.get((state, symbol), None)
    return push


def decide(tm):
    # We try to find a cps certificate using closure() over small automata.
    # Budget: limited enumeration. We try n = 1, 2, 3 states per side.
    for n in (1, 2, 3):
        tables = list(_push_tables(n, 200000))
        # Deduplicate by push function behaviour on reachable states.
        seen = set()
        uniq = []
        for t in tables:
            key = tuple(sorted(t.items()))
            if key not in seen:
                seen.add(key)
                uniq.append(t)
        for lt in uniq:
            blank_l = 0
            pl = _make_push(lt, blank_l)
            for rt in uniq:
                blank_r = 0
                pr = _make_push(rt, blank_r)
                try:
                    cert = closure(pl, pr)
                except Exception:
                    cert = None
                if cert is not None:
                    try:
                        from neverhalt.kernel import check
                        check(tm, cert)
                        return cert
                    except Reject:
                        pass
    return None
