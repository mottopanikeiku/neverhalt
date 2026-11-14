import sys
from neverhalt.tm import parse
from neverhalt.helpers import closure
from neverhalt.kernel import check

# Build all deterministic automata over symbols {0,1} with up to K states.
# States are integers 0..K-1. State 0 is the all-blank half-tape, and must
# loop on symbol 0: push_blank(0, 0) == 0.
# The other states are free.
def all_automata(K):
    # transitions[s][x] = next state, or None meaning "never happens".
    # We enumerate one transition table per symbol: for K states, K^K choices.
    import itertools
    out = []
    for sym in range(2):
        pass
    # We need a pair (left, right) of push functions sharing the same
    # transition tables. The helper takes push_left and push_right, so an
    # automaton is determined by a list [t0, t1] with t0[0] == 0.
    # Enumerate all pairs of tables per symbol independently.
    tables = []
    for K in range(1, 4):
        if K == 1:
            # only state 0, must loop on 0; on 1 it can stay or be null
            for t1 in (0, None):
                tbl = {0: 0, 1: t1}
                tables.append(tbl)
        else:
            # enumerate K^K tables for symbol 1 (symbol 0 fixed: state 0 -> 0,
            # other states free)
            for combo in itertools.product(range(K) + (None,), repeat=K):
                # state 0 must map to 0 on symbol 0
                tbl = {0: 0}
                for s in range(1, K):
                    tbl[s] = combo[s - 1]
                tables.append(tbl)
    return tables

def make_push(table):
    def push(state, symbol):
        return table.get(symbol, {}).get(state)
    return push

def build_pairs(K):
    # We want pairs (left, right) of automata of the same size, each with
    # state 0 looping on 0. Enumerate tables for symbol 0 (must have 0->0)
    # and symbol 1.
    import itertools
    pairs = []
    for size in range(1, K + 1):
        if size == 1:
            t0_opts = [{0: 0}]
        else:
            t0_opts = []
            for combo in itertools.product(range(size) + (None,), repeat=size):
                t = {0: 0}
                for s in range(1, size):
                    t[s] = combo[s - 1]
                t0_opts.append(t)
        for t0 in t0_opts:
            for t1 in t0_opts:
                # left and right are independent automata; we need pairs of
                # (left table, right table) where each table has two symbols.
                # We'll enumerate a single table for left and one for right.
                pairs.append((t0, t1, t0, t1))
    return pairs

def decide(tm):
    # Parse the machine to get its transition structure.
    table, ns, nsym = parse(tm)
    # Kernel limits: 5000 states per automaton, 200000 contexts.
    K = 3
    # Enumerate automata pairs of small size.
    # An automaton is (size, t0, t1) where t0 is the transition on symbol 0
    # (with t0[0] == 0) and t1 on symbol 1.
    import itertools

    def enum_tables(size):
        if size == 1:
            yield {0: 0}
            return
        # symbol-0 table: state 0 -> 0, other states free (including None)
        for combo in itertools.product(range(size) + (None,), repeat=size):
            t = {0: 0}
            for s in range(1, size):
                t[s] = combo[s - 1]
            yield t

    def make_push(t0, t1):
        def push(state, symbol):
            tbl = t0 if symbol == 0 else t1
            return tbl.get(state)
        return push

    seen = set()
    for size in range(1, K + 1):
        tables = list(enum_tables(size))
        for t0 in tables:
            for t1 in tables:
                key = (size, tuple(sorted(t0.items())), tuple(sorted(t1.items())))
                if key in seen:
                    continue
                seen.add(key)
                push_l = make_push(t0, t1)
                push_r = make_push(t0, t1)
                try:
                    cert = closure(push_l, push_r, cap=200000)
                except Exception:
                    cert = None
                if cert is not None:
                    try:
                        check(tm, cert)
                    except Exception:
                        continue
                    return cert
    return None