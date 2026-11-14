from neverhalt.tm import parse, run
from neverhalt.helpers import closure

# Enumerate small automata per side and test the CPS closure directly.
def _enum_tables(max_states):
    # each table: list of transitions; table[state][sym] -> next state or None
    # state 0 must loop on 0 (state 0 loops on symbol 0)
    tables = []
    for n in range(1, max_states + 1):
        # enumerate all functions from states x symbols -> states, with state 0 on 0 -> 0
        # to keep this feasible we only enumerate up to 2 symbols and small state counts
        def rec(state, sym, acc):
            if state == n and sym == 2:
                tables.append([list(a) for a in acc])
                return
            if state == n:
                rec(0, sym + 1, acc)
                return
            if sym == 2:
                rec(state + 1, 0, acc)
            else:
                if state == 0 and sym == 0:
                    acc[state][sym] = 0
                    rec(state, sym + 1, acc)
                else:
                    for nxt in range(n):
                        acc[state][sym] = nxt
                        rec(state, sym + 1, acc)
        acc = [[0, 0] for _ in range(n)]
        rec(0, 0, acc)
    return tables

# build transition tables actually used by the machine (halt transitions are absent)
def _machine_tables(tm):
    table, n_states, _ = parse(tm)
    return table, n_states

def decide(tm):
    table, n_states = _machine_tables(tm)
    # We need automaton tables mapping state -> per-symbol next state (None = never).
    # Our enumeration uses ints 0..n-1; convert to lists where missing transitions are None.
    # We limit to 2 symbols since the tape is binary.
    tables = _enum_tables(2)
    for lt in tables:
        # left automaton: push_left(state, symbol) -> next state; blank_left = 0
        # build push functions
        def make_push(t):
            def push(state, sym):
                if sym == 0:
                    return t[state][0]
                if sym == 1:
                    return t[state][1]
                return None
            return push
        pl = make_push(lt)
        for rt in tables:
            pr = make_push(rt)
            cert = closure(table, n_states, pl, pr, blank_left=0, blank_right=0, cap=200000)
            if cert is not None:
                return cert
    return None
