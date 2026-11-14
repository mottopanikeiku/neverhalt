import sys
from neverhalt.tm import parse
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure


def _all_tables(n):
    """Every deterministic automaton table for a half-tape with n states.
    Table is a list of lists: table[state][symbol] = next state.
    State 0 is the all-blank half-tape and must loop on symbol 0:
    table[0][0] == 0.  Only transitions actually used by the closure
    survive the certificate (null elsewhere)."""
    out = []
    for combo in range((n * n) ** n):
        table = []
        x = combo
        for _ in range(n):
            row = []
            for _ in range(2):
                row.append(x % n)
                x //= n
            table.append(row)
        if table[0][0] != 0:
            continue
        out.append(table)
    return out


def _push_of(table):
    def push(state, symbol):
        return table[state][symbol]
    return push


def decide(tm):
    table, n_states, n_symbols = parse(tm)
    # state 0 is A; halting transitions are absent from the table
    for n in (1, 2, 3):
        tabs = _all_tables(n)
        for lt in tabs:
            for rt in tabs:
                # only try to build a closure once per pair
                try:
                    cert = closure(
                        _push_of(lt), _push_of(rt),
                        blank_left=0, blank_right=0, cap=200000,
                    )
                except Exception:
                    cert = None
                if cert is None:
                    continue
                # verify before returning anything
                try:
                    check(tm, cert)
                    return cert
                except Reject:
                    continue
        # beyond 3 states this decider has nothing to offer
        if n == 3:
            return None
    return None


NAME = "cps_small_search"