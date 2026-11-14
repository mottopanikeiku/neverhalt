import sys
sys.setrecursionlimit(100000)

from neverhalt.tm import parse
from neverhalt.helpers import closure

# Build all small left/right automata (push functions) with 1..3 states.
# State 0 = all-blank half-tape (must loop on 0). Other states can do anything.
# A push function maps (state, symbol) -> state. We cap at 3 states per side.

def build_automata(max_states):
    auts = []
    # enumerate transition tables for states 1..max_states-1, symbols 0/1
    # each non-zero state has 2 entries, each in 0..max_states-1
    import itertools
    n = max_states - 1
    for combo in itertools.product(range(max_states), repeat=2*n):
        table = {0: (0, 0)}
        for st in range(1, max_states):
            table[st] = (combo[2*(st-1)], combo[2*(st-1)+1])
        auts.append(table)
    return auts

def make_push(table):
    def push(state, symbol):
        return table[state][symbol]
    return push

# Try pairs of automata; first closure with no halting context wins.
def decide(tm):
    table, ns, nsym = parse(tm)
    # quick check: skip if we can't parse
    for ms in (1, 2, 3):
        Ls = build_automata(ms)
        Rs = build_automata(ms)
        for lt in Ls:
            for rt in Rs:
                if ms == 1 and lt != Rs[0]:
                    pass
                try:
                    cert = closure(make_push(lt), make_push(rt), blank_left=0, blank_right=0)
                except Exception:
                    cert = None
                if cert is not None:
                    return cert
    return None
